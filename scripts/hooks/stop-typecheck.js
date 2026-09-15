#!/usr/bin/env node
/**
 * stop-typecheck.js
 * Stop hook: runs tsc --noEmit for TypeScript projects touched this session.
 *
 * Non-blocking: outputs findings but exits 0 so the Stop event is not blocked.
 * Outputs [REQUIRED ACTION] when errors are found so Claude invokes typescript-reviewer.
 */

'use strict'

const { execSync } = require('child_process')
const fs = require('fs')
const path = require('path')

const ACCUM_FILE = path.join(process.cwd(), '.claude', '.ts-edited-files')

function findNearestTsconfig(filePath) {
  let dir = path.resolve(path.dirname(filePath))
  const root = path.resolve(process.cwd())

  while (dir.startsWith(root)) {
    const tsconfig = path.join(dir, 'tsconfig.json')
    if (fs.existsSync(tsconfig)) {
      return { dir, tsconfig }
    }
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }

  const rootTsconfig = path.join(root, 'tsconfig.json')
  if (fs.existsSync(rootTsconfig)) {
    return { dir: root, tsconfig: rootTsconfig }
  }
  return null
}

function localTscFor(dir) {
  const exe = process.platform === 'win32' ? 'tsc.cmd' : 'tsc'
  let cur = dir
  const root = path.resolve(process.cwd())

  while (cur.startsWith(root)) {
    const candidate = path.join(cur, 'node_modules', '.bin', exe)
    if (fs.existsSync(candidate)) {
      return candidate
    }
    const parent = path.dirname(cur)
    if (parent === cur) break
    cur = parent
  }
  return null
}

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  process.stdout.write(input)

  if (!fs.existsSync(ACCUM_FILE)) process.exit(0)

  const edited = fs.readFileSync(ACCUM_FILE, 'utf8').split('\n').filter(Boolean)
  fs.writeFileSync(ACCUM_FILE, '')

  if (edited.length === 0) process.exit(0)

  const projects = new Map()
  for (const file of edited) {
    const project = findNearestTsconfig(file)
    if (project) {
      projects.set(project.tsconfig, project)
    }
  }

  if (projects.size === 0) {
    process.stderr.write('[typecheck] No tsconfig.json found for edited TypeScript files; skipping\n')
    process.exit(0)
  }

  for (const project of projects.values()) {
    const label = path.relative(process.cwd(), project.tsconfig)
    process.stderr.write(`[typecheck] Running tsc --noEmit for ${label}...\n`)

    const localTsc = localTscFor(project.dir)
    if (!localTsc) {
      const dirLabel = path.relative(process.cwd(), project.dir) || '.'
      process.stderr.write(`[typecheck] TypeScript is not installed for ${dirLabel}; run npm install in that package\n`)
      continue
    }

    try {
      execSync(`"${localTsc}" --noEmit -p "${project.tsconfig}"`, {
        cwd: project.dir,
        stdio: 'pipe',
        timeout: 60000,
      })
      process.stderr.write(`[typecheck] ${label}: no errors\n`)
    } catch (err) {
      const out = (err.stdout || '').toString().trim()
      const errout = (err.stderr || '').toString().trim()
      const combined = [out, errout].filter(Boolean).join('\n')
      if (combined) {
        process.stderr.write(`[typecheck] TypeScript errors found:\n${combined}\n`)
        process.stderr.write('[REQUIRED ACTION] TypeScript errors were found in files you edited this session. You MUST now use the typescript-reviewer agent to fix them before this response ends. This is mandatory, not optional.\n')
      }
    }
  }

  process.exit(0)
})
