# How to Integrate AgentForge with External Tools

> **Path convention.** Paths shown as `docs/…`, `agentforge/…` or `agentforge_custom_plugin/…` are in the AgentForge **Assets** repo. Only `docs/guides/` ships into a target (as `agentic-assets/docs/guides/`), so those are written as plain paths rather than links — a link would resolve in Assets and dangle in every target. Code does ship: `install.py` copies `agentforge/src/` to the same path in the target, and `simulator/` to **`agentforge_simulator/`**.

> **Who this is for.** You want AgentForge to talk to GitHub, Jira, Confluence, Zephyr, or any
> other system of record — pushing artifacts out, pulling existing ones in, or syncing test
> results. This guide gives the architecture, the transport decision and its reasoning, and the
> concrete steps to add a provider.
>
> **Where this file lives.** Shipped from the Assets repo's `docs/guides/`; `install.py` /
> `update_agentforge_claude_project.py` copy it to **`<target>/agentic-assets/docs/guides/`**.
> That is *not* `neuroedge/docs/guides/`, which is the target project's own documentation and is
> never overwritten by an update.
>
> **Status legend:** ✅ built and usable · ⚠️ built but with a caveat · ❌ not built yet.
> Read `docs/decisions/TECH-DEBT.md` (`decisions/TECH-DEBT.md`) entry **TD-016** alongside this
> guide — it holds the current gaps and their evidence. **Only GitHub outbound has run against a
> real external system** (4/4 live tests passed 2026-07-29, TD-016). Inbound pull is unproven, and
> the Jira, Zephyr and TestRail paths have no live test in `agentforge/tests/` — treat those as the
> design you are implementing, not a proven path.

---

## 1. Decision: use the direct API, not MCP

**For bulk work, call the vendor's REST API from code. Reserve MCP for interactive lookups.**

This repo declares 27 MCP servers, including `jira` (`mcp-atlassian`), `github`
(`server-github`) and `confluence` (`confluence-mcp-server`). They are genuinely useful — just
not for this job. Three cost terms decide it:

| | MCP | Direct API in code |
|---|---|---|
| Tool schemas | occupy context whether called or not | none |
| **Response payload** | every tool result is a message the model reads; Jira/Confluence JSON is large and deeply nested | parsed in-process — only what you print enters context |
| Round-trips | one model turn per call | N calls in one turn |

The middle row dominates. Pushing 400 test-case results through MCP means 400 tool results in
context; through the API it is one call and one summary line.

**What MCP buys you, so the trade is clear:** the server owns auth, pagination, retry and
API-version drift, and it degrades gracefully when a vendor changes a schema. A direct client
owns all of that. The trade flips with volume — hence a split, not a ban:

- **Bulk / structured / repeatable** → API. Artifact push, corpus pull, test-result sync.
- **Interactive / few-item / exploratory** → MCP. *"What's blocking PROJ-412?"*

> This supersedes ADR-0012's blanket "MCP-first transport" for the bulk paths. Also decisive:
> **there is no Zephyr MCP server** (nor TestRail/TM4J/Xray), so test management cannot go
> through MCP at all.

---

## 2. Architecture

### 2.1 One base interface per boundary, many providers

AgentForge uses **`typing.Protocol`** (structural typing), not inheritance. Your provider does
**not** import or subclass anything — it just has the right methods. That keeps your code free
of AgentForge imports and independently testable.

There are two boundaries. Pick the one that matches your system:

**`ExchangeAdapter`** — artifacts and run-state, in both directions.
`agentforge/src/exchange/adapter.py` ✅

```python
class ExchangeAdapter(Protocol):
    def push(self, record_path: Path) -> PushResult: ...
    def pull_intents(self) -> PullResult: ...
    def pull_artifacts(self) -> PullArtifactsResult: ...
```

**`TestManagementAdapter`** — test results to a test-management vendor.
`agentforge/src/qa/adapter.py` ✅

```python
class TestManagementAdapter(Protocol):
    def upload_junit_xml(self, path: Path) -> UploadResult: ...
```

**What is built behind each boundary today:**

| Boundary | Implementations | Selected by |
|---|---|---|
| `ExchangeAdapter` | `git` → `exchange/git_adapter.py` (gh CLI) · `github` → `exchange/github_adapter.py` (REST, stdlib) · `NoneExchangeAdapter` · `MisconfiguredExchangeAdapter` | `choice` in `exchange_config.json` (Step 3, §3a) |
| `TestManagementAdapter` | `ZephyrAdapter` → `qa/zephyr_adapter.py` (Zephyr **Scale** only: `POST /v2/automations/executions/junit`, Bearer token) · `TestRailAdapter` → `qa/testrail_adapter.py` (wraps `trcli parse_junit`, writes each TC-ID into the `test_id` property first) · `NoneAdapter` | `qa/vendor_config.py` choice `zephyr_scale`, `testrail` or `none` (`unset` / `decide_later` → `NoneAdapter`); pushed only by `/test-run --push` and `/test-plan --push` |
| Jira (PM lane — no Protocol) | `pm/jira_sync.py` → `push_sprint_backlog()`, `push_issue_status()`, returning `SyncResult(success, reason)` | `pm/jira_config.py` choice `jira` / `none`, which the sprint-planning skill reads from `.claude/pm/jira-config.json` |
| Confluence | none in `agentforge/src/` — only the `confluence` MCP server | — |

`jira_sync.py` contains no HTTP client: the Jira call is an injected `jira_tool` callable (for
example the Jira MCP tool). With none supplied it returns `success=False`, "no Jira tool
available — repo-local only".

### 2.2 The result objects — verified signatures

```python
PushResult(success: bool, detail: str = "")
PullResult(success: bool, intents: list[DriveIntent], detail: str = "")
PullArtifactsResult(success: bool, docs: list[IngestedDoc], detail: str = "")

IngestedDoc(source_id: str, locator: str, content: str)
DriveIntent(action: str, target: str, identity: str, raw_id: str = "")
UploadResult(success: bool, detail: str = "")
```

### 2.3 Three invariants you must honour

**RESULT-OBJECT-NEVER-RAISE.** No exception may escape your methods. Every failure — network,
auth, timeout, malformed response — returns `success=False` with a human-readable `detail`.
The existing adapters do this without exception, and callers rely on it: an integration must
never be the reason a stage fails.

**No-vendor is a legitimate choice, not a degraded mode.** `NoneExchangeAdapter` and
`NoneAdapter` are first-class fallbacks — *"not a stub to delete once a real adapter exists."*
Never make a provider mandatory, and never treat "nothing configured" as an error.

**Fail closed on configuration.** `ExchangeConfig.drivers` and `ingest_sources` are
allowlists: an unlisted identity or source is **rejected**, never silently permitted. A corrupt
config loads as empty and refuses, rather than defaulting open.

### 2.4 Idempotency for inbound

Reuse `exchange/ledger.py`'s `AppliedIntentLedger` — do not write your own. It keys on
`f"{source_id}:{locator}:{content_hash}"`, so a changed document at the same locator is new work
while an unchanged one on a re-pull is not.

**Watch out:** a real system may change a document's *locator* while its content is stable, or
expose a server-side revision id instead of a content hash. Decide how you map that onto the
ledger key before you pull anything twice.

---

## 3. Steps to add a provider

Worked example uses **GitHub** (partly built). Substitute Jira, Confluence or Zephyr as needed.

### Step 1 — Confirm the API and auth

| System | API | Auth |
|---|---|---|
| GitHub | REST + GraphQL | PAT or GitHub App |
| Jira | Cloud REST v3 for issues, **plus** Jira Software/Agile REST for sprints & boards | email + API token (Basic) or OAuth 2.0 |
| Confluence | Cloud REST v2 | same Atlassian token as Jira |
| Zephyr | ⚠️ **three different products** — Scale (ex-TM4J), Squad Cloud, Enterprise — each with a different API and auth. The built `ZephyrAdapter` targets **Scale** | **separate token from Jira** |
| TestRail | vendor CLI `trcli` (`trcli parse_junit`), which the built `TestRailAdapter` shells out to | API key (`TESTRAIL_API_KEY`); `trcli` must be on `PATH` (`pip install trcli`) |

> **Two traps.** Jira sprint/board writes live in a *different* API from issue writes — if you
> need `push_sprint_backlog`, plan for the Agile API specifically. And Zephyr's API is separate
> from Jira's despite being a Jira app: **connecting Jira gives you nothing for test
> management.** Pick the Zephyr product before writing code.

### Step 2 — Write the provider class

Put it in `agentforge/src/exchange/<name>_adapter.py` (or `qa/` for test management). Inject the
transport so it is testable without credentials — mirror `GitExchangeAdapter`, which takes an
injected runner:

```python
# agentforge/src/exchange/jira_adapter.py
from dataclasses import dataclass
from pathlib import Path
from exchange.adapter import PullResult, PushResult, PullArtifactsResult

@dataclass
class JiraExchangeAdapter:
    """Satisfies ExchangeAdapter structurally — no import of it required."""

    # Injected so unit tests need no network and no credentials.
    request: callable          # (method, url, **kw) -> response-like
    base_url: str

    def push(self, record_path: Path) -> PushResult:
        try:
            ...                                  # your API calls
            return PushResult(success=True, detail="pushed 12 issues")
        except Exception as exc:                  # noqa: BLE001 — never escapes
            return PushResult(success=False, detail=f"jira push failed: {exc}")

    def pull_intents(self) -> PullResult:
        return PullResult(success=True, intents=[], detail="no drive intents")

    def pull_artifacts(self) -> PullArtifactsResult:
        return PullArtifactsResult(success=True, docs=[], detail="not implemented")
```

Implement only what you need — return an honest `success=True` with a "not implemented" detail
for verbs you do not support, rather than raising.

### Step 3 — Register it

✅ **Built.** `exchange/config.py` resolves providers from a registry, so adding one needs
no core edit:

```python
from exchange.config import register_provider
from my_target.jira_adapter import JiraExchangeAdapter

register_provider("jira", lambda: JiraExchangeAdapter.from_env())
```

Then select it in `exchange_config.json` (the exchange CLI's `--config-path` default —
`exchange.json` is the *record* it builds, not the config):

```json
{ "choice": "jira" }
```

`choice` remains a free-form string, so `"git"` and `"github"` keep working unchanged.
Call `register_provider()` from code your target already runs — a coded tool, a
`conftest.py`, or an `agentforge_custom_plugin` module. Re-registering an existing name
replaces it, so you can also override `github` with an enterprise variant.

The registry covers `ExchangeAdapter` only. `qa/vendor_config.py` is still a closed enum
(`zephyr_scale`, `testrail`, `none`) with an `if` chain in `get_adapter()`, so adding a
test-management vendor **does** need a core edit there.

**Why an explicit call and not an import path in config.** A config string naming
`module:ClassName` would turn a hand-edited `exchange_config.json` into arbitrary code execution
at adapter-resolution time. Credentials in config are inert data; an import path is not —
so the two are not equivalent even though both are "user-supplied config". This keeps the
same fail-closed posture `drivers` and `ingest_sources` already use.

**Failure behaviour, by design.** A bad provider name is **reported, not silently
ignored** — it resolves to `MisconfiguredExchangeAdapter`, which is deliberately distinct
from `NoneExchangeAdapter`:

| Config | Adapter | Meaning |
|---|---|---|
| `unset` / `none` / absent | `NoneExchangeAdapter` | you chose no vendor — legitimate, silent |
| a name in the registry | your provider | working |
| a name **not** in the registry, or a factory that raises | `MisconfiguredExchangeAdapter` | **you chose a vendor and we could not honour it** |

The misconfigured case prints `[exchange] CONFIG ERROR: …` to stderr **and** returns the
same reason in every result object's `detail`, naming the bad value and listing the known
providers. It still never raises — `get_adapter()` is called inside stage execution, and
an integration must not be the reason a stage dies.

Why this matters: silently degrading a typo to "no vendor" meant `"choice": "githbu"`
pushed nothing, looked like a clean run, and left the operator believing the integration
was live.

### Step 4 — Credentials

**Never commit a credential** (Hard Rule 1). `plugins/mcp-servers.json` holds placeholders
(`YOUR_JIRA_API_TOKEN_HERE`) and must keep holding placeholders.

- Read from the **environment** in your adapter.
- For local development, `.claude/settings.local.json` is gitignored.
- Use a **throwaway sandbox** — a scratch GitHub repo, a free Jira project — never a customer
  tenant.
- Missing credentials must degrade to `success=False` with a clear detail, **not** a crash and
  not a silent no-op.

**Which variables the built pieces actually read** (from the code, not the template):

| Piece | Environment variables | Read in |
|---|---|---|
| `github` exchange provider | `AGENTFORGE_GITHUB_REPO` (`owner/name`), `GITHUB_TOKEN` (falls back to `GITHUB_PAT`) | `exchange/github_adapter.py` `from_env()` |
| Zephyr Scale | `ZEPHYR_BASE_URL`, `ZEPHYR_API_TOKEN` | `qa/vendor_config.py` |
| TestRail | `TESTRAIL_BASE_URL`, `TESTRAIL_API_KEY` | `qa/vendor_config.py` |
| `jira` / `github` / `confluence` MCP servers | `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` · `GITHUB_PERSONAL_ACCESS_TOKEN` · `CONFLUENCE_BASE_URL`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN` | `plugins/mcp-servers.json` (in a target: `agentic-assets/plugins/mcp-servers.json`) |

> `.env.example` uses these same names (`ZEPHYR_*`, `TESTRAIL_*`). The TestRail adapter also needs
> `trcli` on PATH; `ZephyrAdapter` supports Zephyr Scale only.

**Where the templates land.** `install.py` seeds `.env.example` into the target root once and
never overwrites it, and copies `settings.local.json.example` to `.claude/settings.local.json`
only if that file is absent (its `env` block carries only ML keys: `ROBOFLOW_API_KEY`,
`HF_TOKEN`, `KAGGLE_USERNAME`, `KAGGLE_KEY`). `.env.example` also carries the
`/marketing-video` keys (`PEXELS_API_KEY`, `PIXABAY_API_KEY`, `OPENAI_API_KEY`,
`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ANTHROPIC_API_KEY`, `NEUROEDGE_VISION_MODEL`) —
no adapter in this guide reads them; see `how_to_create_marketing_video.md`.

### Step 5 — Test it in two layers

**Unit — no credentials, always runs.** Inject a fake transport. Assert the never-raise
contract explicitly: make the fake raise, and check you still get `success=False`.

```python
def test_push_never_raises_when_transport_raises():
    def boom(*a, **kw): raise RuntimeError("network down")
    result = JiraExchangeAdapter(request=boom, base_url="x").push(Path("rec.json"))
    assert result.success is False
```

**Integration — credentialed, excluded by default.** Mark with `-m integration` and make it
**skip loudly** when credentials are absent — a silent skip is indistinguishable from a pass:

```python
@pytest.mark.integration
def test_push_to_real_sandbox():
    token = os.environ.get("JIRA_API_TOKEN")
    if not token:
        pytest.skip("JIRA_API_TOKEN unset — this test did NOT verify the live API")
    ...
```

Run: `pytest -m integration -p no:name_of_plugin`
(the `-p no:name_of_plugin` flag is mandatory repo-wide — without it a failing suite can exit `0`).

### Step 6 — Verify honestly

Green unit tests prove the never-raise contract and nothing else. Before claiming an integration
works, confirm **the external system accepted what you sent** by looking at it — the issue
created, the page updated, the results visible. Record what you observed.

---

## 3a. Using it: the `/exchange` command — export, import, apply

Once a provider is configured you drive the boundary through **one command**, `/exchange`
(backed by `agentforge/src/exchange/exchange_cli.py`). **There is no
`/agentforge-import` or `/agentforge-export`, and none should be added** — a second
surface for the same job guarantees the two drift.

### 3a.1 Configure once

```bash
/exchange                      # first run prompts for a provider and persists the answer
```

Or write the config by hand — **`exchange_config.json`**, the `--config-path` default.
(`exchange.json` is the record `export` builds, `--record-path`. The other defaults are
`run.json`, `gates.json`, `exchange_ledger.json` and `exchange_audit.json`, all in the current
directory.)

```json
{
  "choice": "github",
  "auto_export": false,
  "drivers": {},
  "ingest_sources": {}
}
```

| Key | Meaning |
|---|---|
| `choice` | provider key — `github`, `git`, `none`, `unset`, or any name you registered. A name that is not registered is **reported**, not silently ignored |
| `auto_export` | whether the orchestrator projects outbound on stage transitions. **Default `false`** — see §3a.4 |
| `drivers` | per-identity allowlist of permitted inbound actions. **Fail-closed**: an unlisted identity is refused |
| `ingest_sources` | allowlist of inbound source ids → local corpus roots. Also fail-closed |

Everything runs with **no provider configured at all** — `NoneExchangeAdapter` keeps the
manifest local and reports "not projected". That is a legitimate choice, not a degraded mode.

### 3a.2 Outbound — `export`

```bash
/exchange export
# or directly — agentforge/src must be importable:
PYTHONPATH=agentforge/src python agentforge/src/exchange/exchange_cli.py export
```

> Without `PYTHONPATH` a direct run fails with `ModuleNotFoundError: No module named 'exchange'`
> — the script's bootstrap puts only `agentforge/src/state/` on `sys.path`.

Builds an **`ExchangeRecord`** from `run.json` + `gates.json`, saves it to `exchange.json`, and pushes it. The record is a
compact **manifest**, not a document bundle:

| Field | Contents |
|---|---|
| `objective`, `current_stage` | where the run is |
| `stages` | stage id → status |
| `gates` | gate states, including `blocked, awaiting-human` |
| `blocked_on` | artifacts with a pending **hard** gate |
| `artifacts` | artifact **paths**, de-duplicated — paths, not file contents |

**Read-only against local state.** `exchange_record.build` never mutates `run.json` or
`gates.json`, so exporting cannot corrupt a run — which is what makes automating it safe.

### 3a.3 Inbound — `import-intents` and `apply`

```bash
/exchange import-intents      # show what is pending. Mutates NOTHING.
/exchange apply               # actually drive the run from inbound intents
```

An external agent drives by opening an Issue labelled `agentforge:<action>`; the title is
the target artifact. `import-intents` is the safe dry-run; `apply` acts.

> **The hard-gate fence is load-bearing and has no override.** An `approve_gate` intent (or
> any other) aimed at a pending **hard** gate is **always refused**. Clearing a hard gate is
> exclusively a human act via `gate_state.py decide` in the main session. An unrecognised
> action is **skipped and counted**, never guessed at.

### 3a.4 Why export can be automatic and import cannot

This asymmetry is deliberate. Do not "fix" it.

| | Trigger | Reason |
|---|---|---|
| **`export`** | **Automatic**, opt-in via `auto_export` | Idempotent, additive, read-only against local state. Nothing local can break by exporting too often |
| **`import-intents` / `apply`** | **Explicit, always** | They **mutate local state from an outside source**. ADR-0012 Direction 2's review gate and draft-vs-binding marker exist to force a human decision; auto-importing would defeat machinery built to prevent exactly that |

There is deliberately **no `auto_import` flag**, and a test
(`test_there_is_no_auto_import_flag`) fails if someone adds one.

**Turning auto-export on** (in `exchange_config.json`):

```json
{ "choice": "github", "auto_export": true }
```

Then the orchestrator exports **at gate transitions and terminal stages** — *not* all 18.
**Every `push()` writes a commit** (measured on the first live GitHub run), so exporting on
every transition would leave 18 `chore(agentforge): publish exchange record` commits per run
in your repository. Gate and terminal stages carry the signal a monitor needs; the rest is
noise.

Fail-closed by design: `auto_export` must be a real JSON `true`. `"yes"`, `1` and `"true"`
all read as **false**, so a hand-edit cannot accidentally start committing. It also requires
a configured provider — enabled with none would export once per stage for nothing.

**Never fails a stage.** Same contract as `pm/refresh.py`: reports and exits 0.

### 3a.5 Quick reference

| Want | Do |
|---|---|
| Pick / change provider | `/exchange` (prompts), or edit `choice` |
| Push current run-state now | `/exchange export` |
| See pending inbound intents, change nothing | `/exchange import-intents` |
| Act on inbound intents | `/exchange apply` |
| Push automatically at gates | `"auto_export": true` |
| Turn everything off | `"choice": "none"` |
| Diagnose a bad provider name | run any verb — the reason is on stderr and in `detail` |

---

## 3b. Rehearse against a simulated system — `agentforge_simulator/`

Before anything talks to a real system, you can point it at the data-source simulator.
`install.py` ships the Assets `simulator/` to **`<target>/agentforge_simulator/`**. Author changes
in Assets, not in the installed copy (`python install.py --project <path> --verify` flags
drift). The first argument picks the mode:

| Mode | Invocation | Stands in for |
|---|---|---|
| **Replay** | `python agentforge_simulator/simulator.py --transport <name> …` | a data **producer**: replays `sim_input/` files and logs what left to `sim_output/` |
| **Scenario** | `python agentforge_simulator/simulator.py --scenario <scenario.yaml> [--hub <id>] [--play-once]` | the external **systems** a use case calls: HTTP routes, role fixtures, tool servers, models, a broker and a database |

### 3b.1 Replay mode — transports

| `--transport` | Key flags (defaults from `--help`) |
|---|---|
| `console` (default) | — |
| `sse` | `--sse-host` (127.0.0.1) `--sse-port` (8080) `--sse-path` (`/events`) `--sse-wait` |
| `mqtt` | `--mqtt-host` (127.0.0.1) `--mqtt-port` (1883) `--mqtt-topic` (`neuroedge/sim`) `--mqtt-qos` `--mqtt-username` `--mqtt-password` `--mqtt-client-id` |
| `webhook` | `--webhook-url` |
| `api` | `--api-url` `--api-method` (POST) `--api-bearer` `--api-header 'K: V'` (repeatable) |

`--http-timeout` (10 s) applies to webhook and api. Pacing is `--rate`, `--loop` (`-1` = forever)
and `--limit`. Every emission is a `{seq, ts, source, kind, payload}` envelope. A connect or send
failure aborts the run with `ERROR:`; nothing is retried.

To generate input instead of capturing it, run
`python agentforge_simulator/gen_input.py --profile <edge_device|sensor|enterprise_ops|cyclic_multichannel>`.
`cyclic_multichannel` adds `--channel-names`, `--rows-per-cycle`,
`--drift {none,ramp,ramp-recover,step}`, `--label-threshold` and `--recipe`. Pin `--seed` together
with `--start-ts` for byte-identical reruns. Full flag reference: `agentforge_simulator/README.md`.

### 3b.2 Scenario mode — simulated external systems

Copy `agentforge_simulator/scenarios/_base/` beside your use case and fill it in.

- **`scenario.yaml`** is the index: `scenario`, `seed`, `clock.compression`, optional `entities` /
  `timeline` CSVs, and `hubs:`. Each hub declares `port`, `sim`, `env`, `capture_topics` and the
  adapters `api` / `mqtt`. An optional `shared:` section holds systems several hubs call, and an
  optional top-level `caller_key` names the caller.
- **`sim.yaml`** belongs to each hub. It lists `systems:`, each with `id`, `description`, `routes`,
  `fixtures`, `seed`, `models` and `mcp`.
- The loader refuses a misspelled key by name.

Each process serves every face from **one stub server on one port**:

| Face | Address | Authored in | Behaviour |
|---|---|---|---|
| Path routes | exact `(method, path)` | `routes/*.routes.json` (`{"routes": [...]}`) | `response` · `capture` + `required` (422 when a field is missing) · `respond_from` · `feed` (`{"rows": [...], "cursor": n}`) · `latency_ms` / `error_rate` drawn from the seeded RNG |
| Role fixtures | `GET` / `POST /<role>/<capability>`; role = the system `id` | `fixtures/*.json` (a list or `{"fixtures": [...]}`; entry keys `capability`, `caller`, `returns` xor `sequence`, `faults`, `matches`) | most specific wins: (role, caller, capability) + `matches` → (role, caller, capability) → (role, capability) + `matches` → (role, capability) → 404 |
| Tool server (MCP) | `/mcp/<server_id>` | `mcp/servers.json` (**generated**; must declare `"source": "discovery-cache"` or it is refused) + `mcp/responses.json` (authored) | JSON-RPC `initialize`, `tools/list`, `tools/call`; a tool the file does not advertise cannot be called |
| Model | `/models/<model_ref>` | `models/responses.json` (`model_ref`, optional `prompt_fingerprint`, `returns`) | canned answers; the fingerprint covers `prompt` / `input` / `question` / `text`; a miss is a 404, never a call to a real provider |
| Queue capture | broker subscription | hub `capture_topics` (MQTT wildcards `+` / `#` refused) | records each message, per topic, into the run log |
| Database | SQLite file under `run/` | `seed/*.csv` | one table per CSV stem |
| Timeline | — | CSV `offset_ms, hub, adapter, target, payload` | `adapter` is `mqtt` (target = topic), `webhook` (target = URL) or `feed`; payloads go out raw, not in the replay envelope |

**Caller identity.** A caller sends `X-NeuroEdge-Caller: key=value;key=value`. The key that names
the caller defaults to `caller`; a bundle overrides it with `caller_key`, which must be non-empty
and must not contain `=` or `;` — the loader refuses those. An absent or malformed header falls
back to the shared-fact answer. Send the header in every environment, not only the simulated one,
or the simulated run exercises a different wire shape.

**The address is the switch.** Point a capability at the simulator by putting a loopback address
in the hub's `env:` overlay, and go real by putting the production address back in the same
field. Ports are declared, and `port: 0` asks the OS for one. Each process writes what it bound
(`endpoints`, `tool_servers`, `ports`, `database`) to `run/ports.<scope>.json` —
`ports.all.json` when run without `--hub`. By default the process serves until stopped;
`--play-once` exits when the timeline ends. Anything unconfigured answers a **loud 404** naming
what was tried.

**Dependencies.** `pip install -r agentforge_simulator/requirements.txt` installs both groups,
including PyYAML for scenario mode. `agentic-assets/requirements-agentforge.txt` includes that file
along with every other AgentForge tool's dependencies. A host that consumes the same transports should reference
`-r agentforge_simulator/requirements-transports.txt` (`paho-mqtt`, `requests`).

---

## 4. Known gaps — read before you start

| Gap | Impact on you |
|---|---|
| ✅ **Provider registry built** | `register_provider()` — no core edit needed (Step 3) |
| ✅ **Two GitHub providers, both supported** | `git` (gh CLI, unchanged) and `github` (REST, stdlib-only, no binary dependency). Prefer `github` in new targets |
| ⚠️ **Jira sprint/board write ops unconfirmed** | `push_sprint_backlog` may need the Agile API; verify before scoping |
| ⚠️ **`GitLocalSource` reads the local filesystem only** | Despite the name it has never cloned or fetched. Inbound from a remote is unbuilt |
| ❌ **Claim extraction from unstructured content** | `ingestion/mapper.py`'s `extract_claims` is a deterministic reference implementation over pre-supplied spans, not a live extractor. Auto-authoring context from real SharePoint/Confluence pages needs this built first |
| ⚠️ **Only GitHub outbound has run live** | `test_github_provider.py` collects 37 unit tests (injected fakes); the 4 tests in `test_github_provider_integration.py` **skip loudly** without credentials and passed 4/4 against the real API on 2026-07-29 (TD-016). Elsewhere, expect auth, pagination, rate-limit and error-shape surprises — none of it is knowable from fakes |
| ⚠️ **Zephyr Scale / TestRail adapters built, no live test** | Unit tests use fakes only. `.env.example` names the wrong Zephyr variables (Step 4) |
| ❌ **No Jira or Confluence client** | `pm/jira_sync.py` pushes only through an injected `jira_tool`; Confluence exists only as an MCP server |
| ⚠️ **Direct `exchange_cli.py` runs need `PYTHONPATH=agentforge/src`** | Otherwise `ModuleNotFoundError: No module named 'exchange'` (§3a.2) |
| ⚠️ **Simulator scenario mode needs PyYAML** | No `agentforge_simulator/requirements*.txt` lists it (§3b.2) |
| ⚠️ **`github` inbound `pull_artifacts` not implemented** | Returns an honest empty success with a `detail` saying so, never raises. Outbound push and drive-intent pull are implemented |

---

## 5. Checklist

- [ ] Boundary chosen (`ExchangeAdapter` or `TestManagementAdapter`)
- [ ] API and auth model confirmed — including *which* API for sprints, or *which* Zephyr product
- [ ] Provider class written, transport injected
- [ ] **No method can raise** — proven by a test with a raising fake
- [ ] No-vendor fallback still works
- [ ] Registered with `register_provider()` and selected by `choice` in `exchange_config.json` (a test-management vendor still needs the `vendor_config.py` core edit, knowingly)
- [ ] Credentials from environment; nothing committed; sandbox not production
- [ ] Unit tests pass without credentials
- [ ] Integration tests skip **loudly** without credentials
- [ ] Live run observed in the external system, and recorded

**Related:** `decisions/TECH-DEBT.md` (TD-016) ·
`agentforge_simulator/README.md` and `agentforge_simulator/scenarios/_base/README.md` (simulator) ·
`ADR-0012` (`decisions/ADR-0012-integration-and-interop-boundary.md`) ·
`ADR-0003` (`decisions/ADR-0003-tc-id-dialect-mapping.md`) (TC-ID dialect mapping, for test
management)
