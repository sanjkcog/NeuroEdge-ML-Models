#!/usr/bin/env node
/**
 * post-edit-native-accumulate.js
 * PostToolUse hook — records any C++ or C# (.NET) source file edited this
 * session so stop-native-review.js can require the matching language reviewer
 * (cpp-reviewer / csharp-reviewer) before the response ends.
 *
 * Mirrors post-edit-ts-accumulate.js: accumulate here, act once at Stop. A
 * dedicated accumulation file (not the shared .source-edited-files, which the
 * holistic stop-code-review-reminder.js clears) keeps the two gates independent
 * — a C# edit must trigger BOTH csharp-reviewer (language pass) and the holistic
 * code-reviewer, exactly as a .py edit triggers python-reviewer plus the holistic
 * pass.
 *
 * Excludes test files — a language-review pass is about production source.
 *
 * Accumulation file: .claude/.native-review-files (gitignored, cleared each Stop
 * event by stop-native-review.js). Always exits 0 (non-blocking).
 */

'use strict'

const fs = require('fs')
const path = require('path')

const ACCUM_FILE = path.join(process.cwd(), '.claude', '.native-review-files')

// C++: .cpp .cc .cxx .c++ .hpp .hh .hxx .h++ .h .c  (no dedicated C reviewer;
// .c/.h route to cpp-reviewer as the closest fit). C#: .cs.
const NATIVE_EXT = /\.(cpp|cc|cxx|c\+\+|hpp|hh|hxx|h\+\+|h|c|cs)$/i

function isTestFile(filePath) {
  const normalized = filePath.replace(/\\/g, '/')
  const base = path.basename(normalized)
  return (
    /(^|\/)(tests?|__tests__)\//.test(normalized) ||
    /^test_/.test(base) ||
    /_test\.[^.]+$/.test(base) ||
    /\.(test|spec|tests)\.[^.]+$/.test(base)
  )
}

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  let event
  try { event = JSON.parse(input) } catch { process.exit(0) }

  const filePath = event?.tool_input?.file_path || event?.tool_input?.path || ''
  if (!filePath || !NATIVE_EXT.test(filePath)) process.exit(0)
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
