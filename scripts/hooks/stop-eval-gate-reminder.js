#!/usr/bin/env node
/**
 * stop-eval-gate-reminder.js
 * Stop hook (ADR-0014's third ai-ml hook, specced but unbuilt until ADR-0015 D-1.7):
 * if ML training code was edited this session (per the accumulator that
 * post-edit-ml-leakage.js maintains) and the response is ending, require an
 * ml-eval-reviewer pass before the turn completes.
 *
 * Blocking (exit 2) for the same empirically-established reason as
 * stop-code-review-reminder.js: exit 0 puts the reminder only in the human's
 * transcript, never in the agent's context, and it is consistently missed.
 *
 * One-shot per edit batch, exactly like the code-review gate: the accumulator is
 * cleared unconditionally, so the next Stop attempt succeeds whether or not the
 * review actually ran. The guarantee is "the requirement reached the agent's
 * context once", not "the review happened" — detecting the latter is the
 * reviewer's job, not a regex's.
 */

'use strict'

const fs = require('fs')
const path = require('path')

const ACCUM_FILE = path.join(process.cwd(), '.claude', '.ml-edited-files')

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  process.stdout.write(input)

  if (!fs.existsSync(ACCUM_FILE)) process.exit(0)

  const edited = fs.readFileSync(ACCUM_FILE, 'utf8').split('\n').filter(Boolean)
  fs.writeFileSync(ACCUM_FILE, '')

  if (edited.length === 0) process.exit(0)

  const list = edited.map(f => `  - ${path.relative(process.cwd(), f)}`).join('\n')
  process.stderr.write(`[ml-eval-gate] ML training code edited this session:\n${list}\n`)
  process.stderr.write(
    '[REQUIRED ACTION] ML model/training code was edited this session and has not been through an ' +
    'ml-eval-reviewer pass yet. Before ending this response you MUST invoke the ml-eval-reviewer ' +
    'agent on these files — it checks train/test leakage (including time-series window/split ' +
    'integrity), metric appropriateness, overfit risk, and reproducibility. A leakage or ' +
    'wrong-metric defect invalidates every number the training run will produce, which is why this ' +
    'gate exists (ADR-0014, ADR-0015). If ml-eval-reviewer already ran for these exact files this ' +
    'session, state that explicitly and proceed.\n'
  )
  process.exit(2)
})
