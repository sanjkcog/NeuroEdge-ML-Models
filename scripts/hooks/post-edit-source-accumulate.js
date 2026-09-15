#!/usr/bin/env node
/**
 * post-edit-source-accumulate.js
 * PostToolUse hook — records any source-code file path edited this session,
 * across all languages (including .py/.ts/.tsx, which also get their own
 * dedicated lint/typecheck hooks — this one is for the separate, holistic
 * "code-reviewer MUST BE USED for all code changes" concern).
 *
 * Excludes test files, docs, config, and lockfiles — a holistic review pass
 * is about source changes, not incidental edits.
 *
 * Accumulation file: .claude/.source-edited-files (gitignored, cleared each
 * Stop event by stop-code-review-reminder.js).
 */

'use strict'

const fs = require('fs')
const path = require('path')

const ACCUM_FILE = path.join(process.cwd(), '.claude', '.source-edited-files')

const SOURCE_EXT = /\.(py|ts|tsx|js|jsx|cpp|cc|cxx|h|hpp|go|java|kt|kts|rs|cs|rb|php|swift|scala|c|m|mm|sql|hocon)$/

function isTestFile(filePath) {
  const normalized = filePath.replace(/\\/g, '/')
  const base = path.basename(normalized)
  return (
    // NOTE: deliberately no bare `spec` directory match here (unlike some JS/Jest/RSpec
    // hook templates) — this repo has no `spec/`-as-test-directory convention (its tests
    // live under `tests/`, see tests/CLAUDE.md), and a bare `spec` match false-positives on
    // legitimately-named production directories (e.g. `neuroedge/backend/spec/`, which holds
    // the UseCaseSpec *specification* model, not tests). `.spec.ts`/`.spec.js`-style test
    // filenames are still caught below by the basename pattern.
    /(^|\/)(tests?|__tests__)\//.test(normalized) ||
    /^test_/.test(base) ||
    /_test\.[^.]+$/.test(base) ||
    /\.(test|spec)\.[^.]+$/.test(base)
  )
}

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  let event
  try { event = JSON.parse(input) } catch { process.exit(0) }

  const filePath = event?.tool_input?.file_path || event?.tool_input?.path || ''
  if (!filePath || !SOURCE_EXT.test(filePath)) process.exit(0)
  if (isTestFile(filePath)) process.exit(0)
  if (!fs.existsSync(filePath)) process.exit(0)

  try {
    const existing = fs.existsSync(ACCUM_FILE)
      ? fs.readFileSync(ACCUM_FILE, 'utf8').split('\n').filter(Boolean)
      : []
    if (!existing.includes(filePath)) {
      fs.appendFileSync(ACCUM_FILE, filePath + '\n')
    }
  } catch {
    // non-blocking — ignore write errors
  }
  process.exit(0)
})
