#!/usr/bin/env node
/**
 * post-edit-ml-leakage.js
 * PostToolUse hook on Edit|Write: scans a just-edited Python training script for
 * classic ML data-leakage / reproducibility smells (ADR-0014, ai-ml discipline).
 *
 * Non-blocking (exit 0 always) — like post-edit-py-lint.js, it emits a
 * [REQUIRED ACTION] directive prompting Claude to invoke ml-eval-reviewer when a
 * smell is found. It is a nudge, not a gate: the real review is the agent's job.
 *
 * Heuristic and deliberately conservative — only fires on high-signal patterns, so
 * a hit is worth a look rather than noise everyone learns to ignore.
 */

'use strict'

const fs = require('fs')
const path = require('path')

// Only look at Python files that actually look like ML training code — avoids firing
// on unrelated .py edits.
const ML_HINT = /\b(torch|tensorflow|keras|sklearn|fit\s*\(|DataLoader|train_test_split)\b/

const SMELLS = [
  {
    // scaler/encoder .fit or .fit_transform on X_test / the full X (should fit on train only)
    re: /\.\s*fit(?:_transform)?\s*\(\s*X_test/,
    msg: 'scaler/encoder fit on X_test — fit on TRAIN only, then transform test (data leakage)',
  },
  {
    re: /\.\s*fit\s*\(\s*X\s*[,)]/,
    msg: 'fit(...) on the full X — if X includes val/test, normalization leaks; fit on the train split',
  },
  {
    // model .fit / .predict passing test as if training on it
    re: /\.\s*fit\s*\([^)]*\bX_test\b/,
    msg: 'model.fit called with X_test — test data must never enter training',
  },
  {
    re: /train_test_split\([^)]*\)(?![\s\S]{0,400}random_state)/,
    msg: 'train_test_split without random_state — split is non-reproducible run to run',
  },
]

// Time-series windowing markers — when present, a shuffle-based split is the #1
// TS leakage mode (overlapping windows land on both sides of the split; ADR-0015).
const TS_WINDOWING = /\b(sliding_window|window_size|windowed|stride)\b/
const SHUFFLE_SPLIT = /(random\.shuffle\s*\(|shuffle\s*=\s*True|\.sample\s*\(\s*frac)/

// Reproducibility: ML code that never sets any seed.
const SEED_SET = /(manual_seed|set_seed|random\.seed|np\.random\.seed|tf\.random\.set_seed|seed_everything)/

// Accumulator consumed by stop-eval-gate-reminder.js (ADR-0014's third hook, built
// per ADR-0015 D-1.7): every ML-looking .py edited this session is recorded so the
// Stop hook can require an ml-eval-reviewer pass once per edit batch — same
// accumulator pattern as post-edit-source-accumulate.js / stop-code-review-reminder.js.
const ML_ACCUM_FILE = path.join(process.cwd(), '.claude', '.ml-edited-files')

function accumulate(filePath) {
  try {
    fs.mkdirSync(path.dirname(ML_ACCUM_FILE), { recursive: true })
    const existing = fs.existsSync(ML_ACCUM_FILE)
      ? fs.readFileSync(ML_ACCUM_FILE, 'utf8').split('\n').filter(Boolean)
      : []
    if (!existing.includes(filePath)) {
      existing.push(filePath)
      fs.writeFileSync(ML_ACCUM_FILE, existing.join('\n') + '\n')
    }
  } catch { /* accumulation is best-effort; never block the edit */ }
}

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  let event
  try { event = JSON.parse(input) } catch { process.exit(0) }

  const filePath = event?.tool_input?.file_path || event?.tool_input?.path || ''
  if (!filePath || !/\.py$/.test(filePath)) process.exit(0)
  if (!fs.existsSync(filePath)) process.exit(0)

  let content
  try { content = fs.readFileSync(filePath, 'utf8') } catch { process.exit(0) }
  if (!ML_HINT.test(content)) process.exit(0)

  accumulate(filePath)

  const findings = []
  for (const smell of SMELLS) {
    if (smell.re.test(content)) findings.push(smell.msg)
  }
  // TS-specific: windowed data + a shuffle-based split. Two conditions ANDed so a
  // plain vision loader using shuffle=True (legitimate) never fires.
  if (TS_WINDOWING.test(content) && SHUFFLE_SPLIT.test(content)) {
    findings.push(
      'windowed time-series data split by shuffle — overlapping windows leak across splits; ' +
      'split chronologically or per physical unit BEFORE windowing (ADR-0015)'
    )
  }
  // Only flag a missing seed when the file clearly trains something.
  if (/\.\s*fit\s*\(|for\s+epoch\b|manual_seed|optimizer/.test(content) && !SEED_SET.test(content)) {
    findings.push('no random seed set — training is not reproducible (set torch/tf/numpy/python seeds)')
  }

  if (findings.length > 0) {
    const base = path.basename(filePath)
    console.log(
      `[ml-leakage] Potential ML issues in ${base}:\n` +
      findings.map(f => '  - ' + f).join('\n') +
      `\n[REQUIRED ACTION] Invoke the ml-eval-reviewer agent on ${base} to confirm/clear these before handoff.`
    )
  }

  process.exit(0)
})
