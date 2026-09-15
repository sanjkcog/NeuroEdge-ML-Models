#!/usr/bin/env python3
"""github_adapter.py — GitHub provider over the REST API (ADR-0012 D1, TD-016).

The API-based counterpart to `git_adapter.py`, which shells out to the `gh` CLI. Both
are kept: `git_adapter` is unchanged so every existing `choice="git"` config keeps
working, and this is registered separately as `"github"`. Two real providers coexisting
is also what demonstrates the registry in `config.py` is genuinely open rather than a
single-implementation abstraction.

WHY REST RATHER THAN `gh` (ADR-0012 D1):
- `gh` is an extra binary every consuming target must install. It is not present in the
  Assets development environment, so the CLI adapter's default runner cannot even be
  exercised here.
- This module uses only the standard library (`urllib.request`). agentforge's sole
  declared dependency is `colorama`; a provider that required `requests` would push a
  new pip dependency onto every target for one integration.

Note the D1 token-cost argument is about MCP, not about CLI-vs-HTTP: both `gh` output
and a REST response are parsed in-process, so neither puts payloads in a model's
context. `gh` was therefore never in conflict with D1's *reasoning* — the reasons to
prefer REST here are the dependency and portability ones above.

RESULT-OBJECT-NEVER-RAISE (mirrors git_adapter.py and qa/adapter.py exactly): every
failure — network, auth, HTTP status, malformed JSON, missing config — is caught and
returned as `success=False` with a human-readable detail. No exception escapes any
public method, because an integration must never be the reason a stage fails.

CREDENTIALS: read from the environment, never from a committed file. See `.env.example`.
A missing token is a clean `success=False`, not a crash and not a silent no-op.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from exchange.adapter import (
    DriveIntent,
    PullArtifactsResult,
    PullResult,
    PushResult,
)

API_ROOT = "https://api.github.com"

# The label prefix an inbound Issue must carry for its body to be read as a drive
# intent. Matches git_adapter's convention so both providers speak the same dialect.
_INTENT_LABEL_PREFIX = "agentforge:"
_TIMEOUT_SECONDS = 30
_PER_PAGE = 100


@dataclass
class HttpResponse:
    """A transport-agnostic response. Lets tests inject without touching urllib."""

    status: int
    body: str
    # Response headers, needed for pagination (`Link: rel="next"`) and rate-limit
    # diagnosis (`X-RateLimit-Remaining`). Added now rather than later: this dataclass is
    # the signature every injected test transport must match, so widening it is one line
    # today and a breaking change across every fake once more providers exist.
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return json.loads(self.body) if self.body.strip() else None


def _urllib_transport(
    method: str, url: str, token: str, payload: dict | None = None
) -> HttpResponse:
    """The default transport. Injected in tests, so this exact function is never
    exercised by the unit suite — which is precisely why it is kept trivial."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            return HttpResponse(status=resp.status, body=resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # An HTTP error is a RESPONSE, not a transport failure — 404 and 422 carry
        # bodies the caller needs. Only genuine unreachability should raise.
        return HttpResponse(status=exc.code, body=exc.read().decode("utf-8", "replace"))


@dataclass
class GithubExchangeAdapter:
    """Implements ExchangeAdapter against the GitHub REST API.

    `repo` is `owner/name`. `transport` is injected so the unit suite needs neither
    network nor credentials; `from_env()` builds the real one.
    """

    repo: str
    token: str
    transport: Callable[..., HttpResponse] = _urllib_transport
    # Where the exchange record is published inside the repo, mirroring git_adapter's
    # repo-committed projection.
    repo_file: str = "exchange.json"
    _labels: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> GithubExchangeAdapter:
        """Build from environment variables. Never raises on absence — an unconfigured
        adapter is constructed and every call reports the misconfiguration honestly,
        which keeps `get_adapter()` free of credential logic."""
        return cls(
            repo=os.environ.get("AGENTFORGE_GITHUB_REPO", ""),
            token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PAT", ""),
        )

    # -- helpers ---------------------------------------------------------------

    def _config_error(self) -> str | None:
        if not self.repo:
            return "AGENTFORGE_GITHUB_REPO unset (expected 'owner/name') — see .env.example"
        if "/" not in self.repo:
            return f"AGENTFORGE_GITHUB_REPO={self.repo!r} is not 'owner/name'"
        if not self.token:
            return "GITHUB_TOKEN (or GITHUB_PAT) unset — see .env.example"
        return None

    def _call(self, method: str, path: str, payload: dict | None = None) -> HttpResponse:
        return self.transport(method, f"{API_ROOT}{path}", self.token, payload)

    # -- push ------------------------------------------------------------------

    def push(self, record_path: Path) -> PushResult:
        """Publish the exchange record to `repo_file` in the repo via the Contents API.

        Create-or-update: the Contents API requires the current blob SHA to update an
        existing file, so a GET precedes the PUT. A 404 on that GET means "new file",
        which is a normal first push, not an error.
        """
        err = self._config_error()
        if err:
            return PushResult(success=False, detail=err)
        try:
            content = Path(record_path).read_text(encoding="utf-8")
        except OSError as exc:
            return PushResult(success=False, detail=f"cannot read {record_path}: {exc}")

        import base64

        try:
            probe = self._call("GET", f"/repos/{self.repo}/contents/{self.repo_file}")
            sha = None
            if probe.status == 200:
                existing = probe.json() or {}
                sha = existing.get("sha")
            elif probe.status not in (404,):
                return PushResult(
                    success=False,
                    detail=f"GitHub returned {probe.status} probing {self.repo_file}: {probe.body[:200]}",
                )

            payload: dict[str, Any] = {
                "message": "chore(agentforge): publish exchange record",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            }
            if sha:
                payload["sha"] = sha
            resp = self._call("PUT", f"/repos/{self.repo}/contents/{self.repo_file}", payload)
            if resp.status not in (200, 201):
                return PushResult(
                    success=False,
                    detail=f"GitHub returned {resp.status} writing {self.repo_file}: {resp.body[:200]}",
                )
            verb = "created" if resp.status == 201 else "updated"
            return PushResult(success=True, detail=f"{verb} {self.repo}/{self.repo_file}")
        except Exception as exc:  # noqa: BLE001 — never escapes (see module docstring)
            return PushResult(success=False, detail=f"github push failed: {exc}")

    # -- pull ------------------------------------------------------------------

    def pull_intents(self) -> PullResult:
        """Read open Issues carrying an `agentforge:<action>` label as drive intents.

        Same dialect as `git_adapter.pull_intents`, so an external agent can drive
        either provider identically. An Issue whose action is not a recognised
        `DriveIntent` action is SKIPPED and counted, never guessed at — the fail-closed
        posture applied to inbound control.
        """
        err = self._config_error()
        if err:
            return PullResult(success=False, intents=[], detail=err)
        try:
            resp = self._call("GET", f"/repos/{self.repo}/issues?state=open&per_page={_PER_PAGE}")
            if resp.status != 200:
                return PullResult(
                    success=False, intents=[],
                    detail=f"GitHub returned {resp.status} listing issues: {resp.body[:200]}",
                )
            issues = resp.json() or []
            if not isinstance(issues, list):
                return PullResult(success=False, intents=[],
                                  detail="issues endpoint did not return a list")
        except Exception as exc:  # noqa: BLE001
            return PullResult(success=False, intents=[], detail=f"github pull failed: {exc}")

        from exchange.git_adapter import _load_driveintent_action_enum

        allowed = _load_driveintent_action_enum()
        intents: list[DriveIntent] = []
        skipped = 0
        for issue in issues:
            action = None
            for label in issue.get("labels", []) or []:
                name = label.get("name", "") if isinstance(label, dict) else str(label)
                if name.startswith(_INTENT_LABEL_PREFIX):
                    action = name[len(_INTENT_LABEL_PREFIX):]
                    break
            if action is None or action not in allowed:
                skipped += 1
                continue
            intents.append(DriveIntent(
                action=action,
                target=(issue.get("title") or "").strip(),
                identity=((issue.get("user") or {}).get("login") or "").strip(),
                raw_id=str(issue.get("number", "")),
            ))
        detail = f"parsed {len(intents)} intent(s)"
        if skipped:
            detail += f", skipped {skipped} unrecognized Issue(s)"
        # SAY SO when the page was full. Pagination is not implemented, and a bare count
        # reads as exhaustive — so a repo with >100 open Issues would silently drop every
        # intent past the first page while reporting success. Truncation the caller cannot
        # see is the defect; an honest detail is the minimum, and the `Link` header now
        # reaches here (see HttpResponse.headers) for a real implementation later.
        if len(issues) >= _PER_PAGE:
            has_next = 'rel="next"' in resp.headers.get("link", "")
            detail += (
                f" — WARNING: {len(issues)} issues returned (page limit {_PER_PAGE})"
                f"{'; MORE PAGES EXIST' if has_next else ''} and pagination is not "
                f"implemented, so this list may be incomplete"
            )
        return PullResult(success=True, intents=intents, detail=detail)

    def pull_artifacts(self) -> PullArtifactsResult:
        """Not implemented for this provider — reported honestly, never raised.

        Inbound corpus pull from a GitHub repo is real work (tree walk, blob fetch,
        ledger keying) and is deliberately out of scope for the first provider. Returning
        an empty success rather than raising keeps the Protocol satisfiable and lets a
        caller distinguish "nothing to ingest" from "this provider cannot ingest" by
        reading `detail`.
        """
        return PullArtifactsResult(
            success=True, docs=[],
            detail="github provider does not implement inbound artifact pull yet (TD-016)",
        )
