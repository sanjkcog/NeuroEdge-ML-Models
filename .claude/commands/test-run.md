# Test Run

Detect the test framework a repo actually uses (never assume, D10), run it via its own
native TC-ID-filtered selection, and collect the JUnit XML every tier-1 runner already
emits natively (D5) — feeding both `/trace-matrix` and whichever test-management vendor
is configured.

This is the standalone command driving the runner registry
(`agentforge/src/qa/runner.py`) built in EP-05 — no existing S10 role agent to share
skills with (see the skill's "Standalone vs. orchestrated" section).

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /test-run · Skills: test-execution, tdd-workflow, verification-loop`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/testing/test-execution.md`
> - `agentic-assets/skills/SDLC/tdd/tdd-workflow.md`
> - `agentic-assets/skills/SDLC/testing/verification-loop.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Domain plugins (auto-discovered)

Product/client-specific context lives in custom plugins under
`agentforge_custom_plugin/<Name>/`. Before executing, self-discover: run
`python agentforge_custom_plugin/discover_plugins.py --stage test-run` (or find
`agentforge_custom_plugin/*/plugin.json` directly and read any plugin whose
`wiring.auto_load` is not `false`), and honor its integration data-formats and safety
constraints when interpreting results — a failure touching a named safety constraint is
never a low-priority result. Absence of plugins is normal — never a blocker.

## Usage

```
/test-run
/test-run TC-01-03-*
/test-run --target staging TC-02-*
/test-run --push
```

Flags:
- `--target <name>` — provision the named environment from `test-env.json` before
  running (up / health-probe / seed), and tear it down afterward regardless of outcome.
  A name with no matching `test-env.json` entry runs locally with no provisioning — this
  is not an error.
- `--push` — after collecting the JUnit XML, also attempt an upload via the configured
  test-management vendor (prompts once if none is configured, D16, among Zephyr Scale /
  TestRail / none / decide later). Never required — the run and its JUnit XML exist
  fully with no vendor at all (D12).
  - Zephyr Scale: set `ZEPHYR_BASE_URL` and `ZEPHYR_API_TOKEN` in the environment.
  - TestRail: set `TESTRAIL_BASE_URL` and `TESTRAIL_API_KEY` in the environment. Neither
    pair is validated before use — a missing or malformed value is reported as a failed
    upload, never a crash (D12).

## Phase 0 — DETECT

Follow the `test-execution` skill's Procedure exactly, starting with
`detect_all(root)` against the repo root. Ambiguous or no-framework results are reported
to the operator, never silently resolved (D10).

## Phase 1 — PROVISION (only with `--target`)

Load `test-env.json`, provision the named environment if an entry exists, and guarantee
teardown via a `finally`-equivalent — every exit path from this command, success or
failure, must reach teardown once provisioning started.

## Phase 2 — SELECT, EXECUTE, COLLECT

Build the runner's native selector from the TC-ID pattern given (or run everything if
none was given), execute, and collect the JUnit XML. A selector that matches zero tests
is reported explicitly — never a silent full-suite fallback.

## Phase 3 — OPTIONAL PUSH

Only if `--push` was given: check `agentforge/src/qa/vendor_config.py`'s persisted
choice, prompting if unset (main session only, D1). Attempt the upload; a failure is
reported, never silently swallowed, and never blocks the JUnit XML or matrix from
existing (D12).

## Report

```
## Test Execution

- Detected: <runner> (confidence: <N>)
- Target: <none | name>
- Selector: <TC-ID pattern | none>
- Result: <N passed, M failed | 0 tests matched | aborted: <reason>>
- Collected: <path | none>
- Vendor: <none | Zephyr Scale | TestRail> <push result if --push>

> Next: /trace-matrix — correlate this result against neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md.
```

## Standalone vs. orchestrated

- **Standalone (this command):** you run it whenever you want a test-execution read —
  no S10 role agent exists (`qa-automation-engineer` owns S9, writing tests;
  `test-triage` owns S11, classifying results).
- **Inside `/agentforge`:** wired into the orchestrator's `STAGE_SEQUENCE` as the
  `test-run` stage — invoked directly (there is no agent to spawn), between
  `test-automation` (S9) and `triage` (S11), causally right after `build` (S8)
  completes for the run.
