#!/usr/bin/env node
/**
 * post-edit-py-lint.js
 * PostToolUse hook — runs ruff on any .py file that was just written or edited.
 * Exits 0 always (non-blocking); outputs a REQUIRED ACTION directive when lint
 * issues are found so Claude invokes python-reviewer immediately.
 */

'use strict'

const { execSync } = require('child_process')
const path = require('path')
const fs = require('fs')

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  let event
  try { event = JSON.parse(input) } catch { process.exit(0) }

  const filePath = event?.tool_input?.file_path || event?.tool_input?.path || ''
  if (!filePath || !/\.py$/.test(filePath)) process.exit(0)
  if (!fs.existsSync(filePath)) process.exit(0)

  try {
    execSync(`ruff check --output-format=text "${filePath}"`, { stdio: 'pipe' })
  } catch (err) {
    const out = (err.stdout || '').toString().trim()
    if (out) {
      console.log(`[python-lint] ruff findings in ${path.basename(filePath)}:\n${out}`)
      console.log(`[REQUIRED ACTION] A Python file was just edited and ruff found issues. You MUST now use the python-reviewer agent before ending this response. This is mandatory, not optional.`)
    }
  }
  process.exit(0)
})
