#!/usr/bin/env node
/**
 * pre-commit-quality.js
 * PreToolUse hook on Bash: runs lightweight checks before git commit commands.
 *
 * Universal checks:
 *   - staged Python files: ruff check when ruff is available
 *   - staged TS/JS files: console.log scan
 *
 * Optional project gate:
 *   - set AGENTFORGE_COMMIT_TEST_CMD to run a project-specific test command
 */

'use strict'

const { execSync } = require('child_process')

function run(command, options = {}) {
  return execSync(command, { stdio: 'pipe', ...options }).toString()
}

function stagedFiles() {
  try {
    return run('git diff --cached --name-only --diff-filter=ACM')
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
  } catch {
    return []
  }
}

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  let event
  try { event = JSON.parse(input) } catch { process.exit(0) }

  const cmd = (event?.tool_input?.command || '').toString()
  if (!/git\s+commit/.test(cmd)) process.exit(0)

  const errors = []
  const warnings = []
  const files = stagedFiles()

  for (const file of files.filter(f => f.endsWith('.py'))) {
    try {
      run(`ruff check "${file}"`)
    } catch (err) {
      const out = (err.stdout || '').toString().trim()
      if (out) warnings.push(`ruff issues in ${file}:\n${out}`)
    }
  }

  for (const file of files.filter(f => /\.(ts|tsx|js|jsx)$/.test(f))) {
    try {
      const stagedContent = run(`git show ":${file}"`)
      if (/console\.log\s*\(/.test(stagedContent)) {
        warnings.push(`console.log found in staged ${file}`)
      }
    } catch {
      // File may not exist in index on some git edge cases; skip.
    }
  }

  if (process.env.AGENTFORGE_COMMIT_TEST_CMD) {
    try {
      process.stderr.write(`[commit-quality] Running AGENTFORGE_COMMIT_TEST_CMD: ${process.env.AGENTFORGE_COMMIT_TEST_CMD}\n`)
      run(process.env.AGENTFORGE_COMMIT_TEST_CMD, { timeout: 120000 })
    } catch (err) {
      const combined = [
        (err.stdout || '').toString(),
        (err.stderr || '').toString(),
      ].filter(Boolean).join('\n').trim()
      errors.push(`Project commit test command failed.\n${combined.slice(0, 1200)}`)
    }
  }

  if (errors.length > 0) {
    console.error('[commit-quality] BLOCKED:\n' + errors.join('\n'))
    process.exit(2)
  }

  if (warnings.length > 0) {
    console.log('[commit-quality] Warnings (commit allowed but please fix):\n' + warnings.join('\n'))
  }

  process.exit(0)
})
