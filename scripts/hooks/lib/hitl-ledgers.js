/**
 * hitl-ledgers.js
 * Shared gate-ledger discovery for pre-write-hitl-gate.js and stop-hitl-gate.js.
 *
 * Why this exists: both hooks used to read only `<cwd>/gates.json`. Since TD-011/TD-019 the
 * orchestrator writes the ledger into the objective folder —
 * `<root>/docs/project_related/<objective-slug>/03-execution-plan/gates.json`
 * (commands/agentforge.md "State-file paths"), with `<root>` not necessarily `neuroedge/`
 * (TD-020). Reading only the cwd path meant a real run's ledger was never found: approvals were
 * never loaded (approved artifacts were not sealed), pending gates were never reported, and every
 * `gh pr create` failed closed on a "missing" ledger.
 *
 * Discovery order:
 *   1. AGENTFORGE_GATES_PATH set  -> that file ONLY (the deterministic test seam).
 *   2. otherwise the UNION of `<cwd>/gates.json` (legacy, and gate_state.py's CLI default
 *      `--path`) when it exists, and every
 *      `**\/docs/project_related/<slug>/03-execution-plan/gates.json` under cwd.
 * Union, not "legacy short-circuits the scan": a stray root gates.json (which agentforge.md
 * calls a bug, and which a forgotten `--path` creates) must not hide the objective ledgers'
 * approvals and pending gates — that would be a fail-open path.
 *
 * The scan is bounded: a `docs/` root is looked for at most MAX_SCAN_DEPTH directories below
 * cwd (deeper roots are out of scope by definition, not "truncated"), and at most
 * MAX_SCAN_DIRS directories are visited. Hitting the directory cap sets `truncated` — callers
 * fail closed on it (gh pr create, and writes to known gated artifacts). Skipped: dot-directories
 * (.git, .venv, ...), node_modules, `archive` (completed objectives), and `agentic-assets` (the
 * self-install copy, which carries its own duplicate ledgers). Symlinked directories are not
 * followed.
 *
 * A ledger is CORRUPT when it is present but either unparseable or structurally invalid by the
 * rules of agentforge/src/state/gate_state.py `_validate` (mirrored in validateLedger below). A
 * malformed individual gate is not skipped: skipping `{"gates": {"pr:main": true}}` would make
 * that PR gate silently vanish (a fail-open path), so the whole ledger is corrupt, naming the key.
 *
 * gates.json keys are project-root-relative forward-slash paths (every real ledger, e.g.
 * `docs/project_related/<slug>/02-project-plan/PRD.md`), or a `<kind>:<name>` key such as
 * `pr:<branch>`. Artifact keys are normalized the same way the hook normalizes the absolute
 * file_path Claude Code sends, so either side may be absolute, `./`-prefixed or backslashed.
 */

'use strict'

const fs = require('fs')
const path = require('path')

const MAX_SCAN_DEPTH = 3
const MAX_SCAN_DIRS = 5000
const SKIP_DIRS = new Set(['node_modules', 'archive', 'agentic-assets', '__pycache__', 'site-packages'])

// Mirrors agentforge/src/state/gates_schema.json, which gate_state._validate reads at runtime.
// Hard-coded because a hook runs in target projects that need not carry the schema file.
const LEDGER_REQUIRED = ['schema_version', 'gates']
const GATE_REQUIRED = ['stage', 'type', 'status', 'decisions']
const STATUS_ENUM = ['pending', 'approved', 'changes_requested', 'rejected']
const TYPE_ENUM = ['hard', 'soft']
const DECISION_REQUIRED = ['identity', 'timestamp', 'outcome']
const OUTCOME_ENUM = ['approved', 'changes_requested', 'rejected']

function isSkippedDir(name) {
  return name.startsWith('.') || SKIP_DIRS.has(name)
}

function isFile(p) {
  try { return fs.statSync(p).isFile() } catch { return false }
}

function isDir(p) {
  try { return fs.statSync(p).isDirectory() } catch { return false }
}

function readDirs(dir) {
  try {
    return fs.readdirSync(dir, { withFileTypes: true }).filter(e => e.isDirectory())
  } catch {
    return [] // unreadable directory: nothing to find there
  }
}

// Project-root-relative, forward-slash form of a file path or artifact key.
function normalizeArtifactPath(filePath, cwd = process.cwd()) {
  if (!filePath) return ''
  const p = String(filePath).replace(/\\/g, '/')
  const abs = path.isAbsolute(p) ? p : path.resolve(cwd, p)
  return path.relative(cwd, abs).replace(/\\/g, '/')
}

// `pr:<branch>` / `ship:<branch>` style keys are identifiers, not paths — kept verbatim.
// Two+ characters before the colon, so a Windows drive letter (`C:`) is still a path.
function normalizeGateKey(key, cwd) {
  return /^[A-Za-z][\w-]+:/.test(key) ? key : normalizeArtifactPath(key, cwd)
}

// AGENTFORGE_GATES_SCAN_MAX_DIRS overrides the directory cap (a positive integer; the test
// seam for the truncation path). Lowering it can only make the hooks fail closed sooner.
function maxScanDirs(env) {
  const n = Number.parseInt(env.AGENTFORGE_GATES_SCAN_MAX_DIRS, 10)
  return Number.isInteger(n) && n > 0 ? n : MAX_SCAN_DIRS
}

function discoverLedgerPaths(cwd = process.cwd(), env = process.env) {
  const dirCap = maxScanDirs(env)
  if (env.AGENTFORGE_GATES_PATH) {
    return { paths: isFile(env.AGENTFORGE_GATES_PATH) ? [env.AGENTFORGE_GATES_PATH] : [], truncated: false, dirCap }
  }

  const paths = []
  const legacy = path.join(cwd, 'gates.json')
  if (isFile(legacy)) paths.push(legacy)

  let truncated = false
  let visited = 0
  const queue = [{ dir: cwd, depth: 0 }]
  while (queue.length) {
    const { dir, depth } = queue.shift()
    if (++visited > dirCap) { truncated = true; break }

    const projectRelated = path.join(dir, 'docs', 'project_related')
    if (isDir(projectRelated)) {
      for (const entry of readDirs(projectRelated)) {
        if (isSkippedDir(entry.name)) continue
        const ledger = path.join(projectRelated, entry.name, '03-execution-plan', 'gates.json')
        if (isFile(ledger)) paths.push(ledger)
      }
    }

    if (depth < MAX_SCAN_DEPTH) {
      for (const entry of readDirs(dir)) {
        if (!isSkippedDir(entry.name)) queue.push({ dir: path.join(dir, entry.name), depth: depth + 1 })
      }
    }
  }
  return { paths, truncated, dirCap }
}

// `<slug>` for `.../project_related/<slug>/03-execution-plan/gates.json`, else null.
function objectiveSlug(ledgerPath) {
  const planDir = path.dirname(ledgerPath)
  if (path.basename(planDir) !== '03-execution-plan') return null
  return path.basename(path.dirname(planDir))
}

const isObject = v => v !== null && typeof v === 'object' && !Array.isArray(v)
const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key)
const repr = v => (typeof v === 'string' ? `'${v}'` : JSON.stringify(v))

/**
 * Mirror of gate_state._validate, same rule order: the first offending field is named, or null
 * when the ledger is valid. `stage` is presence-only there (free-form), so presence-only here.
 */
function validateLedger(data) {
  if (!isObject(data)) return 'top-level value is not an object'
  for (const key of LEDGER_REQUIRED) {
    if (!has(data, key)) return `missing required field '${key}'`
  }
  if (!isObject(data.gates)) return "field 'gates' must be an object"
  for (const [artifact, gate] of Object.entries(data.gates)) {
    const name = `gate ${repr(artifact)}`
    if (!isObject(gate)) return `${name} must be an object`
    for (const key of GATE_REQUIRED) {
      if (!has(gate, key)) return `${name} missing required field '${key}'`
    }
    if (!STATUS_ENUM.includes(gate.status)) {
      return `${name} field 'status' has invalid value ${repr(gate.status)}, expected one of ${STATUS_ENUM.join('|')}`
    }
    if (!TYPE_ENUM.includes(gate.type)) {
      return `${name} field 'type' has invalid value ${repr(gate.type)}, expected one of ${TYPE_ENUM.join('|')}`
    }
    if (!Array.isArray(gate.decisions)) return `${name} field 'decisions' must be an array`
    for (const [i, decision] of gate.decisions.entries()) {
      if (!isObject(decision)) return `${name} decision #${i} must be an object`
      for (const key of DECISION_REQUIRED) {
        if (!has(decision, key)) return `${name} decision #${i} missing required field '${key}'`
      }
      if (!OUTCOME_ENUM.includes(decision.outcome)) {
        return `${name} decision #${i} field 'outcome' has invalid value ${repr(decision.outcome)}, ` +
          `expected one of ${OUTCOME_ENUM.join('|')}`
      }
    }
  }
  return null
}

/**
 * Load every discoverable ledger.
 * Returns { ledgers, corrupt, truncated, dirCap }:
 *   ledgers: [{ file, label, slug, gates: Map<normalizedKey, { key, gate }> }]
 *   corrupt: [{ file, label, error }] — present but unparseable, or invalid per gate_state._validate
 * A ledger that vanishes between discovery and read is simply absent (missing is not corrupt).
 */
function loadLedgers(cwd = process.cwd(), env = process.env) {
  const { paths, truncated, dirCap } = discoverLedgerPaths(cwd, env)
  const ledgers = []
  const corrupt = []
  for (const file of paths) {
    const label = normalizeArtifactPath(file, cwd)
    let data
    try {
      data = JSON.parse(fs.readFileSync(file, 'utf8'))
    } catch (err) {
      if (err && err.code === 'ENOENT') continue
      corrupt.push({ file, label, error: err.message })
      continue
    }
    const invalid = validateLedger(data)
    if (invalid) {
      corrupt.push({ file, label, error: `not a valid gates ledger: ${invalid}` })
      continue
    }
    const gates = new Map()
    for (const [key, gate] of Object.entries(data.gates)) {
      gates.set(normalizeGateKey(key, cwd), { key, gate })
    }
    ledgers.push({ file, label, slug: objectiveSlug(file), gates })
  }
  return { ledgers, corrupt, truncated, dirCap }
}

function describeLedger(ledger) {
  return ledger.slug ? `objective ${ledger.slug} (${ledger.label})` : ledger.label
}

module.exports = {
  MAX_SCAN_DEPTH,
  MAX_SCAN_DIRS,
  discoverLedgerPaths,
  loadLedgers,
  validateLedger,
  normalizeArtifactPath,
  normalizeGateKey,
  objectiveSlug,
  describeLedger,
}
