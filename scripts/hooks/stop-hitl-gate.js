#!/usr/bin/env node
/**
 * stop-hitl-gate.js
 * Stop hook: exits 2 while ANY gate in ANY discovered gates.json ledger is `pending`,
 * injecting [REQUIRED ACTION] into the orchestrator's context so the main session runs
 * the AskUserQuestion approval flow (D1 — a subagent can neither spawn nor ask).
 *
 * Ledger discovery is shared with pre-write-hitl-gate.js (lib/hitl-ledgers.js): the
 * objective-folder ledgers `**\/docs/project_related/<slug>/03-execution-plan/gates.json`
 * plus a legacy `<cwd>/gates.json`, or AGENTFORGE_GATES_PATH alone when set. Pending gates
 * from every ledger are reported, each named by its objective slug, with the exact
 * `--path` to record the decision into.
 *
 * Modelled on stop-code-review-reminder.js's exit-2/stderr mechanism, but NOT
 * on its one-shot semantics: that hook clears its accumulator unconditionally
 * after firing once, regardless of whether the reminder was acted on. Doing
 * the same here would let an unapproved gate stop blocking after a single
 * nudge, contradicting the "100% of decisions recorded" requirement (TS-02-02).
 *
 * The one-shot mechanism here is instead the `status` field itself
 * (gate_state.py, gates-mvp.plan.md Task 1): `pending` is the only status this
 * hook blocks on. Once ANY decision is recorded — approved, changes_requested,
 * or rejected — status leaves `pending` and this hook naturally stops firing
 * for that gate. No second "already asked" flag exists; a write can still be
 * blocked separately (pre-write-hitl-gate.js checks `approved` specifically).
 *
 * type=="soft" gates are excluded from the blocking set: gates_schema.json documents
 * soft as "advisory, does not block writes," and forcing a Stop-response over one
 * would make "advisory" a lie for half of what it's supposed to mean (third-round
 * code-review finding). Mirrors gate_state.GateState.any_pending()'s exclusion in
 * Python — kept independent here since this hook reads gates.json directly, not
 * through gate_state.py.
 *
 * A corrupt ledger (unparseable, or a malformed gate entry per gate_state._validate) is skipped
 * here with a stderr WARNING naming it (pre-write-hitl-gate.js is the fail-closed half): this
 * hook cannot read a decision out of it, and forcing a Stop over it would trap the session.
 * A truncated ledger scan is reported the same way.
 */

'use strict'

const { loadLedgers, describeLedger } = require('./lib/hitl-ledgers')

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  process.stdout.write(input)

  let ledgers, corrupt, truncated, dirCap
  try {
    ({ ledgers, corrupt, truncated, dirCap } = loadLedgers())
  } catch {
    process.exit(0) // discovery itself failed — nothing this hook can act on
  }

  // Skipped, but never silently: a corrupt ledger (unparseable, or a malformed gate entry per
  // gate_state._validate) or a truncated scan may hide pending gates. Reported on stderr without
  // forcing a Stop, so the session is not trapped; pre-write-hitl-gate.js is the fail-closed half.
  if (corrupt.length) {
    process.stderr.write(
      `[hitl-gate] WARNING: skipped unreadable gate ledger(s), pending gates there are not reported: ` +
      `${corrupt.map(c => `${c.label} (${c.error})`).join('; ')}. Repair via gate_state.py.\n`
    )
  }
  if (truncated) {
    process.stderr.write(
      `[hitl-gate] WARNING: the gate-ledger scan hit its directory bound (${dirCap} directories, ` +
      'AGENTFORGE_GATES_SCAN_MAX_DIRS); pending gates in unread ledgers are not reported.\n'
    )
  }

  const sections = []
  for (const ledger of ledgers) {
    const pending = [...ledger.gates.values()].filter(
      ({ gate }) => gate.status === 'pending' && gate.type !== 'soft'
    )
    if (pending.length === 0) continue
    const items = pending.map(({ key, gate }) => `    - ${key} (stage ${gate.stage})`).join('\n')
    sections.push(
      `  ${describeLedger(ledger)} — record with --path "${ledger.label}":\n${items}`
    )
  }
  if (sections.length === 0) process.exit(0)

  process.stderr.write(`[hitl-gate] Gate(s) pending approval:\n${sections.join('\n')}\n`)
  process.stderr.write(
    '[REQUIRED ACTION] One or more gated artifacts are awaiting a decision. ' +
    'You MUST ask the user (AskUserQuestion, main session only — D1) to Approve / ' +
    'Request changes / Reject each one, then record the decision in the ledger named above via ' +
    '`python agentforge/src/state/gate_state.py --path <ledger> decide <artifact> <outcome> ' +
    '--identity <who>`. This is mandatory before ending this response.\n'
  )
  process.exit(2)
})
