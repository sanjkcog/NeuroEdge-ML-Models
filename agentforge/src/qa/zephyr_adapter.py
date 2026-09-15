#!/usr/bin/env python3
"""zephyr_adapter.py — uploads JUnit XML to Zephyr Scale's documented automation endpoint.

Per ADR-0003: Zephyr Scale is the first vendor adapter (US-04-03), chosen over TestRail
by explicit operator direction. Its ingestion mechanism is a single, vendor-documented
REST endpoint (`POST /v2/automations/executions/junit`), not a CLI like TestRail's
`trcli` — so this wraps exactly that one endpoint via stdlib `urllib.request`, never a
broader Zephyr API client (D8's "don't reimplement a REST client" concern, honoured by
scope rather than by using a CLI).
"""

from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from adapter import UploadResult

_JUNIT_ENDPOINT = "/v2/automations/executions/junit"
_TIMEOUT_SECONDS = 30


class ZephyrAdapter:
    """Implements TestManagementAdapter against Zephyr Scale's JUnit-automation endpoint.

    `base_url`/`api_token` are the only configuration this adapter needs — no separate
    Zephyr client library, no MCP (D8). A network failure or a non-2xx response is
    reported as UploadResult(success=False, ...), never raised — the repo-local matrix
    must still render regardless of what happens here (D12).
    """

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    def upload_junit_xml(self, path: Path) -> UploadResult:
        url = f"{self.base_url}{_JUNIT_ENDPOINT}"
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            return UploadResult(
                success=False,
                detail=f"Could not read {path} to upload: {exc}.",
            )
        try:
            request = Request(
                url,
                data=data,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/xml",
                },
            )
            with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                return UploadResult(
                    success=True,
                    detail=f"Uploaded {path} to Zephyr Scale (HTTP {response.status}).",
                )
        except HTTPError as exc:
            return UploadResult(
                success=False,
                detail=f"Zephyr Scale rejected the upload: HTTP {exc.code} {exc.reason}.",
            )
        except URLError as exc:
            return UploadResult(
                success=False,
                detail=f"Could not reach Zephyr Scale: {exc.reason}.",
            )
        except ValueError as exc:
            return UploadResult(
                success=False,
                detail=f"Invalid Zephyr Scale base URL {self.base_url!r}: {exc}.",
            )
