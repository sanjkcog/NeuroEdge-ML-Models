#!/usr/bin/env node
/**
 * post-edit-legacy-risk.js
 * PostToolUse hook - warns when edits touch high-risk legacy surfaces.
 *
 * The hook is intentionally non-blocking. Its job is to force an explicit
 * routing decision before the assistant ends a response after risky edits.
 */

'use strict'

const path = require('path')

let input = ''
process.stdin.on('data', data => (input += data))
process.stdin.on('end', () => {
  let event
  try {
    event = JSON.parse(input)
  } catch {
    process.exit(0)
  }

  const filePath = event?.tool_input?.file_path || event?.tool_input?.path || ''
  if (!filePath) process.exit(0)

  const normalized = filePath.replace(/\\/g, '/').toLowerCase()
  const base = path.basename(normalized)

  const riskyPath =
    /(^|\/)(migrations?|schema|db|database|sql|auth|security|permissions?|roles?|billing|payments?|invoice|orders?|deploy|deployment|infra|infrastructure|scripts|ci|\.github\/workflows)(\/|$)/.test(normalized) ||
    /(dockerfile|docker-compose|compose\.ya?ml|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|requirements.*\.txt|pyproject\.toml|pom\.xml|build\.gradle|settings\.gradle|cargo\.toml|go\.mod|go\.sum)$/.test(base)

  if (!riskyPath) process.exit(0)

  console.log(`[legacy-risk] Edited high-risk legacy surface: ${filePath}`)
  console.log('[REQUIRED ACTION] Before ending this response, state whether `/legacy-audit --risk-only` or the `legacy-modernizer` agent is needed. For data/auth/deploy/security changes, also route to the relevant specialist reviewer and record memory-bank/ADR updates if behavior or architecture changes.')
  process.exit(0)
})
