#!/usr/bin/env python3
"""testrail_adapter.py — uploads JUnit XML to TestRail via the vendor's own `trcli` CLI.

Per ADR-0003/ADR-0004: TestRail is the second vendor adapter (US-05-03), proving the
`TestManagementAdapter` protocol is genuinely pluggable across two structurally
different vendor shapes — Zephyr Scale's single REST endpoint vs. TestRail's
vendor-maintained CLI (`trcli`). This adapter shares no implementation with
`ZephyrAdapter` beyond the protocol itself (ADR-0003's own point about the two
vendors' different maintenance shapes).

TestRail's dialect (ADR-0003): the TC-ID must be written into the `test_id` **property**
on each JUnit `<testcase>` element before `trcli parse_junit` runs — a real translation
step, unlike Zephyr's largely-passthrough correlation. This adapter's injection first
looks for an already-embedded `TC-NN-SS-TT` in each testcase's `name`/`classname`
attribute, and falls back to `runner.scan_tc_id_bindings()` (matching the testcase's
base name, before any `[...]` parametrize suffix, against the source-level `# @tc
TC-NN-SS-TT` comment convention, D9) — a JUnit report generated from a plainly-named
test carries no TC-ID unless something maps it back this way, since the D9 convention
is a source-only annotation invisible at runtime. A testcase with no discoverable TC-ID
either way is left alone and still uploaded — this must never block the whole file
from being pushed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from adapter import UploadResult
from runner import scan_tc_id_bindings

_TC_ID = re.compile(r"TC-\d{2}-\d{2}-\d{2}")
_TIMEOUT_SECONDS = 60


class TestRailAdapter:
    """Implements `TestManagementAdapter` by wrapping `trcli parse_junit`."""

    def __init__(self, base_url: str, api_key: str, project_root: Path | str | None = None):
        self.base_url = base_url
        self.api_key = api_key
        self._project_root = Path(project_root) if project_root is not None else Path(".")
        # Cached across multiple upload_junit_xml() calls on the same instance — the
        # source-comment convention doesn't change mid-process, so a batch upload of
        # several suites shouldn't re-walk and re-read every .py file under the
        # project root for each one.
        self._tc_id_bindings_cache: dict[str, str] | None = None

    def upload_junit_xml(self, path: Path) -> UploadResult:
        path = Path(path)

        if shutil.which("trcli") is None:
            return UploadResult(
                success=False,
                detail="trcli is not on PATH — install it (pip install trcli) to push to TestRail.",
            )

        try:
            self._inject_test_id_properties(path)
        except OSError as exc:
            return UploadResult(
                success=False,
                detail=f"Could not read {path} to upload: {exc}.",
            )
        except ET.ParseError as exc:
            return UploadResult(
                success=False,
                detail=f"Could not parse {path} as JUnit XML: {exc}.",
            )

        cmd = [
            "trcli",
            "-y",
            "--base-url",
            self.base_url,
            "--key",
            self.api_key,
            "parse_junit",
            "--file",
            str(path),
        ]
        try:
            proc = subprocess.run(
                cmd, check=False, timeout=_TIMEOUT_SECONDS, capture_output=True, text=True
            )
        except (FileNotFoundError, PermissionError) as exc:
            return UploadResult(success=False, detail=f"trcli could not be run: {exc}.")
        except subprocess.TimeoutExpired:
            return UploadResult(
                success=False, detail=f"trcli timed out after {_TIMEOUT_SECONDS}s."
            )

        if proc.returncode != 0:
            # Redact the FULL stdout/stderr first, then truncate — truncating first
            # could cut the key in half at the slice boundary, leaving an
            # unredacted fragment of it in the reported detail.
            stdout = self._redact(proc.stdout)
            stderr = self._redact(proc.stderr)
            detail = f"trcli exited {proc.returncode}: {stdout[-1000:]}{stderr[-1000:]}"
            return UploadResult(success=False, detail=detail)
        return UploadResult(success=True, detail=f"Uploaded {path} to TestRail via trcli.")

    def _redact(self, text: str) -> str:
        """Strip the API key out of any text before it's surfaced in a result/log —
        `trcli` echoes its own invocation back on some error paths (e.g. usage
        errors), and `self.api_key` is passed to it as a literal argv element."""
        if self.api_key and self.api_key in text:
            return text.replace(self.api_key, "***REDACTED***")
        return text

    def _inject_test_id_properties(self, path: Path) -> None:
        """Writes each discoverable TC-ID into its `<testcase>`'s `test_id` property.
        Best-effort: a testcase with no discoverable TC-ID (directly embedded or via
        the source-scan fallback) is left untouched, never raised as an error — the
        file still uploads with whatever mapping was found. Idempotent: re-running on
        an already-injected file updates the existing `test_id` value rather than
        appending a duplicate `<property>` element."""
        tree = ET.parse(path)
        root = tree.getroot()
        changed = False

        for testcase in root.iter("testcase"):
            name = testcase.get("name", "")
            classname = testcase.get("classname", "")
            match = _TC_ID.search(f"{classname} {name}")
            tc_id = match.group(0) if match else None

            if tc_id is None:
                if self._tc_id_bindings_cache is None:
                    self._tc_id_bindings_cache = scan_tc_id_bindings(self._project_root)
                tc_id = self._tc_id_bindings_cache.get(name.split("[", 1)[0])

            if tc_id is None:
                continue

            self._set_test_id_property(testcase, tc_id)
            changed = True

        if changed:
            tree.write(path, encoding="utf-8", xml_declaration=True)

    def _set_test_id_property(self, testcase: ET.Element, tc_id: str) -> None:
        properties = testcase.find("properties")
        if properties is None:
            properties = ET.SubElement(testcase, "properties")
        existing = properties.find("property[@name='test_id']")
        if existing is not None:
            existing.set("value", tc_id)
            return
        prop = ET.SubElement(properties, "property")
        prop.set("name", "test_id")
        prop.set("value", tc_id)
