#!/usr/bin/env node
/**
 * post-edit-console-warn.js
 * PostToolUse hook — warns if console.log appears in a just-edited .ts/.tsx/.js file.
 * Non-blocking: exits 0 always.
 */

'use strict'

const fs = require('fs')
const path = require('path')

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  let event
  try { event = JSON.parse(input) } catch { process.exit(0) }

  const filePath = event?.tool_input?.file_path || event?.tool_input?.path || ''
  if (!filePath || !/\.(ts|tsx|js|jsx)$/.test(filePath)) process.exit(0)
  if (!fs.existsSync(filePath)) process.exit(0)

  try {
    const content = fs.readFileSync(filePath, 'utf8')
    const lines = content.split('\n')
    const hits = lines
      .map((l, i) => ({ n: i + 1, l }))
      .filter(({ l }) => /console\.log\s*\(/.test(l) && !l.trimStart().startsWith('//'))

    if (hits.length > 0) {
      const summary = hits.map(h => `  line ${h.n}: ${h.l.trim()}`).join('\n')
      console.log(`[console-warn] console.log found in ${path.basename(filePath)}:\n${summary}`)
      console.log('[console-warn] Remove debug logging before commit.')
    }
  } catch {
    // non-blocking
  }
  process.exit(0)
})
