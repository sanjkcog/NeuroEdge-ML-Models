#!/usr/bin/env node
/**
 * pre-write-hitl-gate.js
 * PreToolUse hook on Write|Edit|Bash: blocks writes to artifacts already gated
 * approved (a hard gate is sealed, not merely acknowledged), and blocks
 * `gh pr create` while the S13 PR gate is unresolved — hard, no override. D3's
 * warn-with-override escape hatch was reversed: the PR gate is now a plain
 * `type: "hard"` gate like any other, tied to S13 `review` (agentforge review —
 * team-lead's fan-in verdict — must exist before the human is even asked; see
 * commands/agentforge.md's "The S13 PR gate" section). There is no bypass path left.
 *
 * gates.json shape and the one-shot design are owned by
 * agentforge/src/state/gate_state.py — this hook only READS ledgers.
 *
 * Ledger discovery lives in lib/hitl-ledgers.js (shared with stop-hitl-gate.js): the
 * objective-folder ledgers `**\/docs/project_related/<slug>/03-execution-plan/gates.json`
 * plus a legacy `<cwd>/gates.json`, or AGENTFORGE_GATES_PATH alone when set. Several
 * objectives can be in flight, so every found ledger is consulted:
 *   - a write is sealed if ANY ledger approved that artifact;
 *   - gh pr create is blocked if ANY ledger blocks it, if NO ledger is found at all,
 *     if any ledger is corrupt, or if the bounded scan was truncated;
 *   - a write to a known hard-gate artifact is blocked if any ledger is corrupt or the scan
 *     was truncated (a seal may sit in the ledger that could not be read).
 *
 * Fail-closed on a corrupt (present but unparseable) ledger, the deliberate INVERSE of
 * pre-commit-quality.js's try/catch-and-continue precedent: it blocks known hard-gate
 * artifact paths (the static fallback list below) and names the file, but still passes
 * through anything not on that list — "fail closed" must not become "block everything
 * forever" for completely unrelated work (gates-mvp.plan.md Task 7 GOTCHA). A MISSING
 * ledger is not a corrupt one: no gate has been opened, so no seal exists to protect, and
 * producers write their artifact BEFORE the orchestrator opens its gate — file writes pass.
 *
 * Ledger tamper resistance. Because a missing ledger lets writes through, removing a ledger
 * would unseal every artifact it approved. So ledgers are protected from the tools themselves:
 *   - a Write/Edit/MultiEdit whose target basename is `gates.json` (or AGENTFORGE_GATES_PATH)
 *     is blocked outright — ledgers are written only by gate_state.py, invoked via Bash `python`;
 *   - a Bash command that combines a destructive operation (delete, move, rename, overwrite,
 *     truncate, in-place edit, copy-onto, output redirection, git rm/mv/checkout/restore/clean/
 *     stash/reset) with a reference to a `gates.json`, its `03-execution-plan` directory, or an
 *     objective folder `project_related/<slug>` is blocked. Read-only references (cat, jq, grep,
 *     git add/diff/commit, gate_state.py itself) pass, as does the documented S16 archive move of a
 *     whole objective folder into `project_related/archive/`.
 * HONEST LIMIT: the Bash detection is best-effort regex/tokenizer matching, exactly like the
 * `gh pr create` detection below — it is not a shell parser and not a sandbox. Known gaps:
 * indirection it cannot see (a script file that deletes the ledger, a variable set in an earlier
 * call, `eval`/encoded commands, a program other than the recognised APIs), path-less repo-wide
 * operations (`git stash`, `git checkout .`, `git reset --hard`, `git clean -fdx`, `rm -rf docs`)
 * that restore or remove a ledger without naming it, a `find -exec cp` onto it, and archiving an
 * objective (after which its artifacts are archived copies, deliberately ungated). The durable
 * control is gate_state.py's audit trail plus version control, not this hook.
 */

'use strict'

const path = require('path')
const { execSync } = require('child_process')
const { loadLedgers, normalizeArtifactPath, describeLedger } = require('./lib/hitl-ledgers')

// Static fallback used ONLY when a ledger exists but cannot be parsed. Single-sourced
// here because gate_state.py's schema carries no such list (it only knows about gates
// that already exist); this hook needs an answer even when a ledger is unreadable.
//
// Paths follow the objective-folder layout producers actually write to (TD-019,
// superseding TD-011 — commands/agentforge.md "Artifact layout"):
// `<root>/docs/project_related/<objective-slug>/NN-*/…`. The `(?:.*\/)?` prefix
// accepts any docs root rather than hard-coding `neuroedge/` (TD-020). `[^/]+` is exactly
// one segment, so archived copies (`archive/<slug>/…`) are deliberately not matched.
// The pre-TD-011 bare forms (`docs/<artifact>.md`, a root `sprint-NN.json`) are gone:
// that layout names a bug, not an artifact (the "no artifact at a bare path" invariant).
const OBJECTIVE_DIR = String.raw`^(?:.*\/)?docs\/project_related\/[^/]+\/`
const HARD_GATE_ARTIFACT_PATTERNS = [
  new RegExp(OBJECTIVE_DIR + String.raw`02-project-plan\/PRD\.md$`),              // S2 requirements
  new RegExp(OBJECTIVE_DIR + String.raw`03-execution-plan\/sprint-[^/]*\.json$`), // S5 sprint-plan
  new RegExp(OBJECTIVE_DIR + String.raw`05-quality\/test-plan\.md$`),             // S6 test-plan
  new RegExp(OBJECTIVE_DIR + String.raw`04-development\/(?:hld|lld)\.md$`),       // S7, ADR-0013
  // Standalone /architecture holds these at a hard gate (commands/architecture.md).
  new RegExp(OBJECTIVE_DIR + String.raw`04-development\/(?:architecture|risk-assessment)\.md$`),
  // S12 is a verdict, not a gates.json entry — kept for parity with the pre-TD-019 list.
  new RegExp(OBJECTIVE_DIR + String.raw`05-quality\/traceability\.md$`),
]

function isKnownHardGateArtifact(normalizedFilePath) {
  return HARD_GATE_ARTIFACT_PATTERNS.some(re => re.test(normalizedFilePath))
}

const LEDGER_ONLY_VIA_GATE_STATE =
  'gates.json ledgers change only through agentforge/src/state/gate_state.py ' +
  '(`python agentforge/src/state/gate_state.py --path <ledger> open|decide|reopen ...`), never by a ' +
  'direct write, delete, move, restore or overwrite — a missing ledger unseals every artifact it approved.'

function isLedgerFile(normalizedFilePath) {
  if (normalizedFilePath.split('/').pop().toLowerCase() === 'gates.json') return true
  const override = process.env.AGENTFORGE_GATES_PATH
  return !!override && normalizeArtifactPath(override).toLowerCase() === normalizedFilePath.toLowerCase()
}

// --- Bash ledger-tamper detection (best-effort; see the header's HONEST LIMIT) -------------

// All matching runs on a lower-cased, backslash-to-slash form of the command.
const TERM = String.raw`(?=$|[\s'"\x60|;&)>])`
const PATH_CHARS = String.raw`[^\s'"\x60|;&)]`
const LEDGER_TARGET_RES = [
  /gates\.json/,                                                        // the ledger itself
  /gates\.[*?[]/,                                                       // a glob that matches it
  new RegExp(String.raw`03-execution-plan/?` + TERM),                   // its directory
  new RegExp(String.raw`03-execution-plan/${PATH_CHARS}*[*?[]`),        // a glob inside that directory
  // The objective folder (or the whole project_related tree, or `project_related/*`) — but not
  // `project_related/archive`, which holds no live ledger.
  new RegExp(String.raw`project_related(?:/(?!archive/?` + TERM + String.raw`)[^/\s'"\x60|;&)]+)?/?\*?` + TERM),
]

const WORD_START = String.raw`(?:^|[\s'"\x60({])`
const WORD_END = String.raw`(?=$|[\s'"\x60();|&])`
const words = list => new RegExp(WORD_START + '(?:' + list.join('|') + ')' + WORD_END)

// Commands that delete, move, rename, overwrite or truncate their operands (POSIX, cmd, PowerShell
// cmdlets and their aliases). New-Item is deliberately absent: `New-Item -ItemType Directory -Force
// .../03-execution-plan` is how a PowerShell run initialises the folder; it is handled per-file below.
const DESTRUCTIVE_VERB_RE = words([
  'rm', 'del', 'erase', 'rmdir', 'rd', 'mv', 'move', 'ren', 'rename', 'unlink', 'rimraf', 'truncate',
  'shred', 'tee', '-delete', 'remove-item', 'ri', 'move-item', 'mi', 'rename-item', 'rni',
  'clear-content', 'clc', 'set-content', 'sc', 'add-content', 'ac', 'out-file',
])
const COPY_VERB_RE = words(['cp', 'copy', 'copy-item', 'cpi', 'xcopy', 'robocopy', 'install', 'ln'])
// Destructive file APIs reachable from `python -c`, `node -e`, or PowerShell .NET calls.
const DESTRUCTIVE_API_RE = new RegExp([
  String.raw`os\.(?:remove|unlink|rename|replace|truncate)\b`, String.raw`shutil\.\w+`, String.raw`rmtree`,
  String.raw`\.unlink\(`, String.raw`\.write_(?:text|bytes)\(`, String.raw`open\([^)]*['"][wax]\+?b?['"]`,
  String.raw`\bfs\.(?:unlink|rm|rmdir|rename|writefile|appendfile|truncate|copyfile)`,
  String.raw`::(?:delete|move|replace|copy|writealltext|writealllines|writeallbytes|appendalltext)\b`,
].join('|'))
const SED_IN_PLACE_RE = new RegExp(WORD_START + String.raw`(?:sed|perl)\s(?:[^|;&]*\s)?(?:-[a-z]*i[a-z.]*|--in-place)(?=\s|=|$)`)
const REDIRECT_TARGET_RE = /(?:^|[^<>=-])(?:\d|&)?>>?\|?\s*("[^"]*"|'[^']*'|[^\s;&|)]+)/g
const DD_TARGET_RE = /(?:^|\s)of=(\S+)/g

const COPY_CMDS = new Set(['cp', 'copy', 'copy-item', 'cpi', 'xcopy', 'robocopy', 'install', 'ln'])
const MOVE_CMDS = new Set(['mv', 'move', 'move-item', 'mi'])
const CONTENT_WRITER_CMDS = new Set(['tee', 'out-file', 'set-content', 'sc', 'add-content', 'ac'])
const NESTED_SHELLS = new Set(['bash', 'sh', 'zsh', 'dash', 'pwsh', 'powershell', 'cmd'])
// Programs that run ANOTHER command named in their arguments. Only inside these may a destructive
// verb appear anywhere in the stage text. For any other program the verb must be the command
// itself, so prose in an argument (a PR body or a --summary that mentions moving a ledger) is not
// an operation.
const COMMAND_RUNNERS = new Set([
  ...NESTED_SHELLS, 'xargs', 'find', 'eval', 'exec', 'nice', 'timeout', 'watch', 'parallel', 'wsl',
  'invoke-expression', 'iex', 'start-process', 'saps', 'start',
])
const DESTRUCTIVE_CMDS = new Set([
  'rm', 'del', 'erase', 'rmdir', 'rd', 'mv', 'move', 'ren', 'rename', 'unlink', 'rimraf', 'truncate',
  'shred', 'remove-item', 'ri', 'move-item', 'mi', 'rename-item', 'rni', 'clear-content', 'clc',
])
const READ_ONLY_CMDS = new Set([
  'cat', 'type', 'jq', 'grep', 'egrep', 'fgrep', 'rg', 'findstr', 'select-string', 'sls', 'get-content',
  'gc', 'head', 'tail', 'less', 'more', 'wc', 'ls', 'dir', 'get-childitem', 'gci', 'stat', 'test-path',
  'echo', 'printf', 'write-host', 'write-output', 'diff', 'file',
])
const GIT_READ_ONLY = new Set(['add', 'diff', 'log', 'show', 'status', 'blame', 'commit', 'grep', 'ls-files', 'cat-file'])
const GIT_DESTRUCTIVE = new Set(['rm', 'mv', 'checkout', 'restore', 'clean', 'stash', 'reset'])
const STATE_CLI_RE = /(?:^|\/)agentforge\/src\/(?:state\/(?:gate_state|run_state)|audit_gates|exchange\/exchange_cli)\.py$/
const STATE_MODULE_RE = /^agentforge\.src\.(?:state\.(?:gate_state|run_state)|audit_gates|exchange\.exchange_cli)$/

// Split on unquoted `;`, `&&`, `||`, `&`, newlines (pipelines) and `|` (stages of a pipeline).
function splitCommand(command) {
  const pipelines = []
  let stages = []
  let cur = ''
  let quote = null
  const endStage = () => { stages.push(cur); cur = '' }
  const endPipeline = () => { endStage(); pipelines.push(stages); stages = [] }
  for (let i = 0; i < command.length; i++) {
    const c = command[i]
    const next = command[i + 1]
    if (quote) {
      cur += c
      if (c === quote) quote = null
      else if (c === '\\' && quote === '"' && /["\\$`]/.test(next || '')) cur += command[++i]
      continue
    }
    if (c === '"' || c === "'") { quote = c; cur += c; continue }
    if (c === '\\' && next !== undefined) { cur += c + command[++i]; continue }
    if (c === '\n' || c === ';') { endPipeline(); continue }
    if ((c === '&' && next === '&') || (c === '|' && next === '|')) { endPipeline(); i++; continue }
    if (c === '|' && command[i - 1] !== '>') { endStage(); continue }
    if (c === '&' && command[i - 1] !== '>' && next !== '>') { endPipeline(); continue }
    cur += c
  }
  endPipeline()
  return pipelines
}

// Whitespace tokens with quotes removed (input is already normalized: no backslashes left).
function tokenize(text) {
  const out = []
  let cur = ''
  let quote = null
  let quoted = false
  for (const c of text) {
    if (quote) { if (c === quote) quote = null; else cur += c; continue }
    if (c === '"' || c === "'") { quote = c; quoted = true; continue }
    if (/\s/.test(c)) { if (cur || quoted) out.push(cur); cur = ''; quoted = false; continue }
    cur += c
  }
  if (cur || quoted) out.push(cur)
  return out
}

// Drop leading env assignments and transparent prefixes so argv[0] is the real command.
function commandWords(text) {
  const argv = tokenize(text)
  while (argv.length && (/^[a-z_][a-z0-9_]*=/.test(argv[0]) || ['sudo', 'command', 'env', 'nohup', 'time', '&', '.'].includes(argv[0]))) {
    argv.shift()
  }
  return argv
}

const commandName = word => (word || '').split('/').pop().replace(/\.exe$/, '')

// Destination operand of a copy/move: an explicit -Destination / -t value, else the last positional.
function destinationOf(argv) {
  for (let i = 1; i < argv.length; i++) {
    if (['-destination', '-t', '--target-directory'].includes(argv[i])) return argv[i + 1] || ''
    const m = argv[i].match(/^--target-directory=(.*)$/)
    if (m) return m[1]
  }
  const positional = argv.slice(1).filter(w => !w.startsWith('-') && !/^\/[a-z?]{1,2}$/.test(w))
  return positional[positional.length - 1] || ''
}

function isStateCliInvocation(argv) {
  let rest = argv
  if (commandName(rest[0]) === 'uv' && rest[1] === 'run') rest = rest.slice(2)
  if (!['python', 'python3', 'py'].includes(commandName(rest[0]))) return false
  for (let i = 1; i < rest.length; i++) {
    if (rest[i] === '-m') return STATE_MODULE_RE.test(rest[i + 1] || '')
    if (!rest[i].startsWith('-')) return STATE_CLI_RE.test(rest[i])
  }
  return false
}

function makeReferenceTest(normalizedCommand) {
  const vars = new Set()
  const assign = /(?:^|[\s;&|(])(?:export\s+)?\$?([a-z_][a-z0-9_]*)\s*=\s*("[^"]*"|'[^']*'|[^\s;&|]+)/g
  for (const m of normalizedCommand.matchAll(assign)) {
    if (LEDGER_TARGET_RES.some(re => re.test(m[2]))) vars.add(m[1])
  }
  const varRes = [...vars].map(v => new RegExp(String.raw`\$(?:\{|env:)?${v}(?![a-z0-9_])`))
  return text => LEDGER_TARGET_RES.some(re => re.test(text)) || varRes.some(re => re.test(text))
}

/**
 * Classify one pipeline stage:
 *   'target' — writes/removes a ledger target through its destination operand (redirect, copy-onto);
 *   'op'     — a destructive operation whose operands must be checked against the pipeline;
 *   null     — not destructive (or a recognised read-only / sanctioned command).
 */
function classifyStage(stage, references) {
  for (const re of [REDIRECT_TARGET_RE, DD_TARGET_RE]) {
    for (const m of stage.matchAll(re)) if (references(m[1])) return 'target'
  }
  const argv = commandWords(stage)
  const cmd = commandName(argv[0])
  const substitutes = /\$\(|`/.test(stage)
  if (['new-item', 'ni'].includes(cmd) && /gates\.json/.test(stage)) return 'target'

  if (!substitutes && (READ_ONLY_CMDS.has(cmd) || isStateCliInvocation(argv))) return null

  // Sanctioned S16 archive (commands/agentforge.md "Archive lifecycle"): move a whole objective
  // folder into project_related/archive/ — only when the ledger file/dir is not named directly.
  const isArchiveMove = moveArgv =>
    /project_related\/archive\//.test(destinationOf(moveArgv)) && !/gates\.json|03-execution-plan/.test(stage)

  if (cmd === 'git') {
    let i = 1
    while (i < argv.length && argv[i].startsWith('-')) i += ['-c', '-C'].includes(argv[i]) ? 2 : 1
    const sub = argv[i]
    if (GIT_READ_ONLY.has(sub) && !substitutes) return null
    if (GIT_DESTRUCTIVE.has(sub)) return sub === 'mv' && isArchiveMove(argv.slice(i)) ? null : 'op'
  }
  if (MOVE_CMDS.has(cmd) && isArchiveMove(argv)) return null
  if (COPY_CMDS.has(cmd)) return references(destinationOf(argv)) ? 'target' : null
  // Content writers take piped CONTENT, not piped paths: only their own file operands matter, so
  // `python gate_state.py --path <ledger> status | tee status.txt` is not a ledger write.
  if (CONTENT_WRITER_CMDS.has(cmd)) return argv.slice(1).some(references) ? 'target' : null
  if (NESTED_SHELLS.has(cmd) && COPY_VERB_RE.test(stage)) return 'op'
  if (DESTRUCTIVE_CMDS.has(cmd)) return 'op'
  if (COMMAND_RUNNERS.has(cmd) && DESTRUCTIVE_VERB_RE.test(stage)) return 'op'
  // Code-shaped calls (os.remove, fs.unlink, sed -i) are unlikely in prose, so match them anywhere.
  if (DESTRUCTIVE_API_RE.test(stage) || SED_IN_PLACE_RE.test(stage)) return 'op'
  return null
}

// The first pipeline that tampers with a ledger target, or null.
function ledgerTamper(command) {
  const normalized = command.replace(/\\/g, '/').toLowerCase()
  const references = makeReferenceTest(normalized)
  if (!references(normalized)) return null // fast path: no ledger target named anywhere
  for (const stages of splitCommand(normalized)) {
    const kinds = stages.map(s => classifyStage(s, references))
    if (kinds.includes('target')) return stages.join('|').trim()
    if (kinds.includes('op') && stages.some(references)) return stages.join('|').trim()
  }
  return null
}

function currentBranch() {
  // Explicitly set (even to '') always wins and is never re-resolved via git — this is
  // the deterministic test seam that lets tests force the "unresolvable" path without
  // needing an actual detached-HEAD checkout.
  if (process.env.AGENTFORGE_PR_BRANCH !== undefined) {
    return process.env.AGENTFORGE_PR_BRANCH || null
  }
  try {
    // A detached HEAD prints an empty string here (not an error) — normalize that to
    // null too, the same "unresolvable" signal as git being entirely unavailable.
    const branch = execSync(
      'git branch --show-current',
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }
    ).trim()
    return branch || null
  } catch {
    return null
  }
}

function block(message) {
  process.stderr.write(`[hitl-gate] BLOCKED: ${message}\n`)
  process.exit(2)
}

function corruptList(corrupt) {
  return corrupt.map(c => `${c.label} (${c.error})`).join('; ')
}

function scanBound(dirCap) {
  return `the gate-ledger scan hit its directory bound (${dirCap} directories, ` +
    'AGENTFORGE_GATES_SCAN_MAX_DIRS) before finishing'
}

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  let event
  try { event = JSON.parse(input) } catch { process.exit(0) }

  const rawFilePath = (event?.tool_input?.file_path || event?.tool_input?.path || '').toString()
  const filePath = normalizeArtifactPath(rawFilePath)
  const command = (event?.tool_input?.command || '').toString()
  const isPrCreate = /gh\s+pr\s+create/.test(command)

  // --- Ledger tamper resistance: independent of what any ledger currently says ---
  if (filePath && isLedgerFile(filePath)) {
    block(`${filePath} is a gate ledger. ${LEDGER_ONLY_VIA_GATE_STATE}`)
  }
  if (command) {
    const tamper = ledgerTamper(command)
    if (tamper) block(`\`${tamper}\` would delete, move, restore or overwrite a gate ledger. ${LEDGER_ONLY_VIA_GATE_STATE}`)
  }

  if (!filePath && !isPrCreate) process.exit(0) // nothing this hook governs — skip the scan

  const { ledgers, corrupt, truncated, dirCap } = loadLedgers()

  // --- File-write path: block only on an artifact already sealed "approved" ---
  if (filePath) {
    // type=="soft" is advisory (gates_schema.json) and is never sealed by approval — a
    // soft gate must not block re-editing regardless of its status, or "advisory" would
    // only be true for the Stop-hook half of the gate (third-round code-review finding,
    // same root cause as stop-hitl-gate.js's own soft-gate exclusion).
    for (const ledger of ledgers) {
      const entry = ledger.gates.get(filePath)
      if (entry && entry.gate.type !== 'soft' && entry.gate.status === 'approved') {
        block(
          `${filePath} is gated (stage ${entry.gate.stage}) and already approved in ` +
          `${describeLedger(ledger)} — editing it requires the orchestrator to explicitly ` +
          're-arm the gate first (`python agentforge/src/state/gate_state.py --path ' +
          `"${ledger.label}" reopen ${entry.key}\`), not a silent overwrite.`
        )
      }
    }
    if (corrupt.length && isKnownHardGateArtifact(filePath)) {
      block(
        `gates.json is unreadable: ${corruptList(corrupt)} — and ${filePath} is a known ` +
        'hard-gate artifact, so failing closed rather than assuming no gate exists.'
      )
    }
    if (truncated && isKnownHardGateArtifact(filePath)) {
      block(
        `${scanBound(dirCap)}, so a ledger that seals ${filePath} may never have been read — ` +
        'failing closed on this known hard-gate artifact. Set AGENTFORGE_GATES_PATH to the ' +
        'objective ledger and retry.'
      )
    }
    if (!isPrCreate) process.exit(0)
  }

  // --- gh pr create path: block while the S13 PR gate is unresolved, no override ---
  if (corrupt.length) {
    // A corrupt ledger must not silently let a PR through with no way to know whether its
    // S13 gate is pending (code-reviewer HIGH finding on the original single-ledger hook).
    block(
      `gates.json is unreadable: ${corruptList(corrupt)} — gh pr create was attempted, ` +
      'failing closed rather than assuming no S13 gate is pending.'
    )
  }
  if (truncated) {
    block(
      `${scanBound(dirCap)}, so an S13 gate may exist in a ledger that was never read — ` +
      'failing closed on gh pr create. Set AGENTFORGE_GATES_PATH to the objective ledger and retry.'
    )
  }
  if (ledgers.length === 0) {
    block(
      'no gates.json ledger found (AGENTFORGE_GATES_PATH, ./gates.json, or ' +
      '**/docs/project_related/<objective-slug>/03-execution-plan/gates.json) and gh pr create ' +
      'was attempted — failing closed rather than assuming no S13 gate is pending.'
    )
  }

  // Keyed by the CURRENT branch specifically, not "any pr:* entry" — a ledger can
  // accumulate one pr:<branch> entry per branch over a project's lifetime, and picking an
  // arbitrary one could evaluate a different branch's already-resolved gate instead of the
  // one that actually applies here (code-reviewer MEDIUM finding).
  const branch = currentBranch()
  if (!branch) {
    // Branch unresolvable (no git, or detached HEAD) — fail CLOSED if anything is PR-gated
    // at all, rather than silently skipping the check (a fail-open path in a fail-closed
    // hook). Identified by key prefix, not gate.type — the PR gate is `type: "hard"` like
    // any other gate since D3's reversal, so type alone no longer disambiguates it.
    const prGated = ledgers.filter(l => [...l.gates.keys()].some(k => k.startsWith('pr:')))
    if (prGated.length) {
      block(
        'could not determine the current branch (no git, or a detached HEAD) — the PR gate ' +
        `that applies here cannot be identified (PR gates exist in ${prGated.map(describeLedger).join(', ')}). ` +
        'Set AGENTFORGE_PR_BRANCH explicitly to the branch name and retry.'
      )
    }
    process.exit(0) // nothing is PR-gated at all — nothing to protect
  }

  const prArtifact = `pr:${branch}`
  const blockers = ledgers
    .map(l => ({ ledger: l, entry: l.gates.get(prArtifact) }))
    .filter(({ entry }) => entry && entry.gate.status !== 'approved')
  if (blockers.length) {
    const detail = blockers
      .map(({ ledger, entry }) => `${entry.gate.status} in ${describeLedger(ledger)}`)
      .join('; ')
    block(
      `S13 PR gate for ${prArtifact} is not approved (${detail}). The agentforge review ` +
      '(team-lead fan-in) must run first, then a human must explicitly approve via ' +
      'gate_state.py decide — there is no override path.'
    )
  }
  process.exit(0)
})
