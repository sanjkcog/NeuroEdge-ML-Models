#!/usr/bin/env node
/**
 * stop-code-review-reminder.js
 * Stop hook: if any source file was edited this session (per
 * post-edit-source-accumulate.js), force a holistic code-reviewer pass
 * before the response ends. This is the general "code-reviewer MUST BE
 * USED for all code changes" gate — separate from the per-file
 * python-reviewer/typescript-reviewer nudges, which only catch lint/type
 * issues, not design/security/reuse concerns.
 *
 * Blocking (exit 2): a Stop hook exiting 2 blocks the stop and feeds stderr
 * back to the agent as required context — exit 0 here previously only
 * surfaced the [REQUIRED ACTION] text in the human's transcript, never in
 * the agent's own context, so the nudge was consistently missed. Confirmed
 * empirically: the accumulator was populated and cleared correctly across a
 * full /prp-implement run, but the agent never acted on it or even
 * mentioned seeing it.
 *
 * The accumulator is cleared unconditionally (blocking or not), so this is
 * a one-shot gate per edit batch, not a persistent lock: once blocked, the
 * very next Stop attempt finds an empty accumulator and succeeds
 * immediately, whether or not code-reviewer actually ran in between. This
 * intentionally does not try to detect "code review actually happened" —
 * it only guarantees the agent's context contains the requirement once, so
 * a compliant agent can no longer claim it never saw it.
 */

'use strict'

const fs = require('fs')
const path = require('path')

const ACCUM_FILE = path.join(process.cwd(), '.claude', '.source-edited-files')

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  process.stdout.write(input)

  if (!fs.existsSync(ACCUM_FILE)) process.exit(0)

  const edited = fs.readFileSync(ACCUM_FILE, 'utf8').split('\n').filter(Boolean)
  fs.writeFileSync(ACCUM_FILE, '')

  if (edited.length === 0) process.exit(0)

  const list = edited.map(f => `  - ${path.relative(process.cwd(), f)}`).join('\n')
  process.stderr.write(`[code-review] Source files edited this session:\n${list}\n`)
  process.stderr.write(
    '[REQUIRED ACTION] Source files were edited this session and have not been through a code-reviewer pass yet. ' +
    'Before ending this response (or before /prp-commit / /prp-pr), you MUST invoke the code-reviewer agent for a ' +
    'holistic review — reuse, simplification, security, and design concerns beyond what lint/typecheck catch. ' +
    'This is mandatory, not optional. If a per-language reviewer (python-reviewer, typescript-reviewer, etc.) ' +
    'already ran for these files this session, code-reviewer is still required as the holistic pass. Simply ' +
    'retrying to end the turn without acting on this defeats the purpose of the gate.\n'
  )
  process.exit(2)
})
