#!/usr/bin/env node
/**
 * session-start-memory-bank.js
 * SessionStart hook: put the memory bank in front of the agent at the start of
 * every session, and state how old each file is.
 *
 * Why this exists (TD-017). The whole token argument rests on an agent
 * re-orienting from a bounded four-file read instead of re-exploring the repo.
 * That only holds if the four files are actually read. Before this hook, "Session
 * Start: read AGENTS.md, ACTIVE.md, PROGRESS.md, REPO_MAP.md" was prose in
 * CLAUDE.md and nothing more — hooks were registered on PreToolUse, PostToolUse
 * and Stop only, so whether a given session loaded the bank depended on whether
 * the model happened to follow the instruction that turn. The fallback when it
 * didn't was whole-repo re-exploration at full input-token cost.
 *
 * Deliberately emits PATHS + AGE, never file contents. Dumping the bank into
 * every session would pay the tokens this mechanism exists to save, and would
 * defeat Layer 0's "pointers, not content" design. The agent is told what exists,
 * how stale it is, and to read it — which is the part that was missing.
 *
 * Staleness thresholds mirror /memory-audit's documented rules (ACTIVE.md > 14
 * days, PROGRESS.md / REPO_MAP.md > 30 days) so a human running the audit and an
 * agent starting a session agree about what "stale" means.
 *
 * Never blocks and never fails a session: any error exits 0 silently. A memory
 * hint is not worth breaking a session over, and a hook that can wedge startup
 * would be removed rather than fixed.
 */

'use strict'

const { execFileSync } = require('child_process')
const fs = require('fs')
const path = require('path')

// Resolve the repo root by walking up to the nearest .git, NOT from process.cwd().
// TD-015 records what cwd-relative resolution costs: the code-review accumulator
// reads its state from cwd, so working across two repos let an edit in one demand
// a review in the other. Same trap, avoided here rather than re-inherited.
function repoRoot(start) {
  let dir = start
  for (;;) {
    if (fs.existsSync(path.join(dir, '.git'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) return null
    dir = parent
  }
}

const BANK = [
  { rel: 'docs/context/ACTIVE.md', staleDays: 14, why: 'current focus + next actions' },
  { rel: 'docs/context/PROGRESS.md', staleDays: 30, why: 'done / in-progress / blocked' },
  { rel: 'docs/context/REPO_MAP.md', staleDays: 30, why: 'where things live' },
  { rel: 'AGENTS.md', staleDays: null, why: 'build/test commands' },
]

const DAY_MS = 24 * 60 * 60 * 1000

/**
 * Age of a file in days, preferring git's last-commit time over filesystem mtime.
 *
 * mtime alone fails in the DANGEROUS direction. Git does not preserve content
 * timestamps across checkout / clone / pull / merge / rebase — any of those reset
 * mtime to "now" regardless of when the content actually last changed. So an
 * ACTIVE.md genuinely untouched for 25 days reads as "0d ago" after a fresh clone
 * or an unrelated pull that happened to touch it, and the staleness flag is
 * suppressed exactly when it matters most. That is a silent false-FRESH, the
 * opposite of the always-cries-stale failure the test suite already guards, so
 * nothing would have caught it.
 *
 * Falls back to mtime when git cannot answer (no git, not a repo, file never
 * committed) — for a never-committed file mtime is in fact the better signal.
 */
function ageDaysOf(root, rel, abs) {
  try {
    // stdio pipes stderr rather than inheriting it — same fix as the stop hook. Against
    // a repo with no commits this printed `fatal: your current branch ... does not have
    // any commits yet` FOUR times (once per bank file) above the memory listing.
    const out = execFileSync('git', ['log', '-1', '--format=%ct', '--', rel], {
      cwd: root, encoding: 'utf8', timeout: 5000, stdio: ['ignore', 'pipe', 'pipe'],
    }).trim()
    if (out) return Math.floor((Date.now() - Number(out) * 1000) / DAY_MS)
  } catch {
    // fall through to mtime
  }
  return Math.floor((Date.now() - fs.statSync(abs).mtimeMs) / DAY_MS)
}

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  try {
    const root = repoRoot(process.cwd())
    if (!root) process.exit(0)

    const lines = []
    const missing = []
    const stale = []

    for (const entry of BANK) {
      const abs = path.join(root, entry.rel)
      if (!fs.existsSync(abs)) {
        missing.push(entry.rel)
        continue
      }
      const ageDays = ageDaysOf(root, entry.rel, abs)
      const isStale = entry.staleDays !== null && ageDays > entry.staleDays
      if (isStale) stale.push(`${entry.rel} (${ageDays}d)`)
      lines.push(
        `  ${entry.rel} — ${entry.why} — last updated ${ageDays}d ago` +
        (isStale ? `  [STALE: >${entry.staleDays}d]` : '')
      )
    }

    if (lines.length === 0 && missing.length === 0) process.exit(0)

    const out = []
    out.push('[memory-bank] Project memory for this session:')
    if (lines.length) out.push(lines.join('\n'))
    if (missing.length) {
      out.push(`  MISSING: ${missing.join(', ')} — run /memory-audit or /legacy-audit --memory-bank`)
    }
    out.push(
      'Read these before non-trivial work — they are the bounded re-orientation read that ' +
      'replaces re-exploring the repo. Update ACTIVE.md and PROGRESS.md after meaningful work.'
    )
    if (stale.length) {
      // Staleness at READ time, not just at audit time: an agent handed a
      // three-week-old ACTIVE.md otherwise consumes it with the same confidence
      // as a fresh one, which /memory-audit's own docs call "worse than none".
      out.push(
        `[memory-bank] STALE: ${stale.join(', ')}. Treat as possibly out of date — ` +
        'verify against the current tree before relying on it, and refresh it as part of this work.'
      )
    }
    process.stdout.write(out.join('\n') + '\n')
  } catch {
    // Never break a session over a memory hint.
  }
  process.exit(0)
})
