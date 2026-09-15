#!/usr/bin/env node
/**
 * post-edit-ts-accumulate.js
 * PostToolUse hook — records .ts/.tsx file paths edited this session.
 * stop-typecheck.js reads this list and runs tsc --noEmit once at Stop.
 *
 * Accumulation file: .claude/.ts-edited-files (gitignored, cleared each session).
 */

'use strict'

const fs = require('fs')
const path = require('path')

const ACCUM_FILE = path.join(process.cwd(), '.claude', '.ts-edited-files')

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  let event
  try { event = JSON.parse(input) } catch { process.exit(0) }

  const filePath = event?.tool_input?.file_path || event?.tool_input?.path || ''
  if (!filePath || !/\.(ts|tsx)$/.test(filePath)) process.exit(0)
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
