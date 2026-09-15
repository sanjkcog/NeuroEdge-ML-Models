#!/usr/bin/env node
/**
 * pre-commit-ml-artifact.js
 * PreToolUse hook on Bash: blocks committing large ML data/weight blobs (ADR-0014,
 * ai-ml discipline). Model weights, datasets, and image dumps belong in a data
 * store / DVC / model registry — not in git, where they bloat history irreversibly.
 *
 * Blocks (exit 2) a `git commit` when a staged file either:
 *   - has a model/data blob extension (.pt/.pth/.onnx/.h5/.ckpt/.safetensors/...), or
 *   - exceeds SIZE_CEILING bytes (a large binary, whatever its extension).
 * Allows (exit 0) everything else — text source, docs, configs commit normally.
 *
 * Env override: AGENTFORGE_ML_BLOB_CEILING (bytes) to tune the size ceiling.
 */

'use strict'

const { execSync } = require('child_process')

const SIZE_CEILING = Number(process.env.AGENTFORGE_ML_BLOB_CEILING) || 25 * 1024 * 1024 // 25 MB

// Model-weight, serialized-model, and bulk-array/dataset extensions. Deliberately
// narrow: these are never legitimately versioned in source, so matching one is a
// high-confidence signal, not a heuristic.
const BLOB_EXT = /\.(pt|pth|onnx|h5|hdf5|ckpt|pb|tflite|safetensors|pkl|pickle|npz|npy|bin|weights|caffemodel|joblib)$/i

function run(command) {
  return execSync(command, { stdio: 'pipe' }).toString()
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

function stagedSize(file) {
  try {
    return Number(run(`git cat-file -s ":${file}"`).trim()) || 0
  } catch {
    return 0
  }
}

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  let event
  try { event = JSON.parse(input) } catch { process.exit(0) }

  const cmd = (event?.tool_input?.command || '').toString()
  if (!/git\s+commit/.test(cmd)) process.exit(0)

  const offenders = []
  for (const file of stagedFiles()) {
    if (BLOB_EXT.test(file)) {
      offenders.push(`${file}  (model/data blob — belongs in a registry/DVC, not git)`)
      continue
    }
    const size = stagedSize(file)
    if (size > SIZE_CEILING) {
      const mb = (size / (1024 * 1024)).toFixed(1)
      offenders.push(`${file}  (${mb} MB > ceiling — too large for git)`)
    }
  }

  if (offenders.length > 0) {
    console.error(
      '[ml-artifact] BLOCKED: ML data/weight blobs must not be committed to git:\n' +
      offenders.map(o => '  - ' + o).join('\n') +
      '\n\nStore datasets/weights in a data store, DVC, or a model registry and reference\n' +
      'them by id/URL (per the ai-ml dataset-sourcing / model-codegen skills). To override a\n' +
      'genuine false positive, `git reset <file>` it, or raise AGENTFORGE_ML_BLOB_CEILING.'
    )
    process.exit(2)
  }

  process.exit(0)
})
