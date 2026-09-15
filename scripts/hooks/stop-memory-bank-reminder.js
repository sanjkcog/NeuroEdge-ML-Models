#!/usr/bin/env node
/**
 * stop-memory-bank-reminder.js
 * Stop hook: when a session changed source but left the memory bank untouched,
 * say so once. WARNS — never blocks.
 *
 * Why this exists (TD-017). "Update ACTIVE.md and PROGRESS.md after meaningful
 * work" is a hard rule with nothing checking it: the four other registered Stop
 * hooks are hitl-gate, typecheck, code-review-reminder and native-review, and
 * none looks at the memory bank. So a session could end with the bank untouched
 * and nothing would say so — which is how the backlog silently becomes fiction
 * while the code is fine (the same shape as TD-014, one layer down).
 *
 * ── WHO ACTUALLY SEES THIS, and why it still exits 0 ───────────────────────
 * Corrected after code review. An earlier version of this comment claimed "the
 * agent sees it" on stderr with exit 0. That is contradicted by first-party
 * measured evidence in stop-code-review-reminder.js:11-17, which records that
 * for a Stop hook, "exit 0 here previously only surfaced the [REQUIRED ACTION]
 * text in the human's transcript, never in the agent's own context, so the nudge
 * was consistently missed. Confirmed empirically."
 *
 * So treat this reminder as HUMAN-FACING. It is not the agent-facing control,
 * and it is not claimed to be.
 *
 * The agent-facing half is session-start-memory-bank.js: SessionStart output IS
 * injected into the session's context, and it reports each bank file's age plus
 * a STALE flag. The loop therefore closes at the START of the next session
 * rather than at the end of this turn — later than ideal, but real, whereas an
 * exit-0 Stop message reaching the agent is measurably not.
 *
 * Exit 0 is kept deliberately rather than escalated to the exit 2 that WOULD
 * reach the agent, because TD-017's own prohibition applies: a hard block on a
 * file an agent can satisfy by appending a blank line buys nothing and trains
 * everyone to write junk edits — it manufactures false evidence of upkeep, which
 * is worse than no gate. stop-code-review-reminder.js correctly DOES block,
 * because a code review cannot be faked by touching a file. The distinction is
 * whether compliance is verifiable, not how important the rule is.
 *
 * Detection is git-based rather than an accumulator file: no state file to go
 * stale, be committed by accident, or leak across repos the way TD-015 records
 * the cwd-relative accumulator doing.
 */

'use strict'

const { execFileSync } = require('child_process')
const fs = require('fs')
const path = require('path')

function repoRoot(start) {
  let dir = start
  for (;;) {
    if (fs.existsSync(path.join(dir, '.git'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) return null
    dir = parent
  }
}

// Kept deliberately IDENTICAL in coverage to post-edit-source-accumulate.js:23.
// `.hocon` and `.sql` were missing here, which mattered more in this repo than
// anywhere else: CLAUDE.md rule 10 makes HOCON agent networks the core design
// principle, and registries/ holds ~100 .hocon files "edited far more often than
// Python" — so the single most common kind of change was invisible to this hook.
// Two hooks disagreeing about what "source" means is the drift; keep them equal.
const SOURCE_EXT = new Set([
  '.py', '.ts', '.tsx', '.js', '.jsx', '.cpp', '.cc', '.cxx', '.h', '.hpp',
  '.go', '.java', '.kt', '.kts', '.rs', '.cs', '.rb', '.php', '.swift',
  '.scala', '.c', '.m', '.mm', '.sql', '.hocon',
])
const BANK = ['docs/context/ACTIVE.md', 'docs/context/PROGRESS.md']

function git(root, args) {
  // stdio pipes stderr instead of inheriting it. execFileSync's DEFAULT inherits the
  // child's stderr straight to this process, so every expected-and-caught git failure
  // leaked raw `fatal: ...` text into the hook's own output, directly above a reminder
  // whose entire value is looking trustworthy to a human. Caught in round-2 review by
  // RUNNING the hook, not reading it — all 21 substring-matching tests passed with the
  // noise present.
  return execFileSync('git', args, {
    cwd: root, encoding: 'utf8', timeout: 5000, stdio: ['ignore', 'pipe', 'pipe'],
  })
}

/**
 * Paths changed in the working tree, via NUL-separated porcelain.
 *
 * `-z` is load-bearing twice over. It disables git's `core.quotepath` quoting, so
 * a non-ASCII filename arrives raw instead of quoted-and-octal-escaped (the old
 * newline parser then ran `.replace(/\\/g,'/')` over those escapes, corrupting
 * them). And it makes renames unambiguous: `R  <new>\0<old>\0`, so the old path
 * can be skipped instead of being glued into one string like
 * "old.py -> new.py" — which broke both the displayed filename and extension
 * matching whenever a rename changed the extension.
 *
 * `-uall` stops untracked DIRECTORIES collapsing to a single `?? pkg/` entry,
 * which hid every source file inside a newly-created package.
 */
function workingTreeChanges(root) {
  const raw = git(root, ['status', '--porcelain', '-uall', '-z'])
  const records = raw.split('\0').filter(Boolean)
  const out = []
  for (let i = 0; i < records.length; i++) {
    const rec = records[i]
    if (rec.length < 4) continue
    const status = rec.slice(0, 2)
    out.push(rec.slice(3))
    // A rename/copy record is followed by its ORIGINAL path as a bare entry.
    if (status[0] === 'R' || status[0] === 'C') i++
  }
  return out
}

/**
 * Paths touched by commits that exist locally but are on no remote.
 *
 * Degradation in a remote-less repo is deliberate and safe: with nothing pushed,
 * every commit counts as unpushed — which also pulls the memory bank into the
 * changed set, so bankTouched short-circuits and the hook stays SILENT. It
 * under-reports there rather than crying wolf, the right direction for an
 * advisory that must stay credible.
 *
 * Without this the hook is silent for any session that COMMITTED its work — at
 * Stop time the tree is clean, `git status` returns nothing, and the reminder
 * never fires. That is not an edge case here: this project ships direct to main
 * and commits mid-session as a matter of course, so the most normal workflow was
 * exactly the one the check could not see.
 */
function committedButUnpushedChanges(root) {
  try {
    // Bail out when the repo has NO remote at all. Without one, "unpushed" means
    // "every commit ever", so the memory bank's own historical commit lands in the
    // changed set, bankTouched short-circuits, and the hook goes PERMANENTLY SILENT.
    // Found by five existing tests failing at once — the first version of this fix
    // traded a wrong answer for no answer, which is worse.
    //
    // With no remote there is no way to bound "this session" from git alone, so this
    // deliberately does not guess: commit inspection is skipped and detection falls
    // back to the working tree. A local-only repo that commits mid-session is a known,
    // stated limitation rather than a silently wrong answer.
    const remotes = git(root, ['for-each-ref', '--format=%(refname)', 'refs/remotes']).trim()
    if (!remotes) return []
    // `HEAD --not --remotes` replaced an `@{upstream}..HEAD` + `HEAD~1..HEAD` pair that
    // was WRONG, and whose own tests could not see it: no test configured a remote, so
    // the upstream range threw in every run and only the fallback was exercised — and
    // `HEAD~1..HEAD` sees exactly ONE commit. Verified empirically: 3 commits with no
    // upstream reported `c.py` alone and silently dropped a.py and b.py.
    //
    // This needs no fallback and no upstream. Verified equal to `@{upstream}..HEAD`
    // where one exists (both returned exactly the 2 unpushed files) and correct across
    // multiple commits where none does.
    //
    // --format= drops commit headers so only paths are emitted; -z keeps them
    // NUL-separated (no quoting) and emits renames as plain paths, no `->` arrow.
    const raw = git(root, ['log', '--name-only', '--format=', '-z', 'HEAD', '--not', '--remotes'])
    return raw.split('\0').filter(Boolean)
  } catch {
    // Unborn HEAD (no commits yet), or git unavailable.
    return []
  }
}

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  process.stdout.write(input)
  try {
    const root = repoRoot(process.cwd())
    if (!root) process.exit(0)

    const changed = [...workingTreeChanges(root), ...committedButUnpushedChanges(root)]
      .map(p => p.replace(/\\/g, '/'))
    const uniq = [...new Set(changed)]

    const source = uniq.filter(p => SOURCE_EXT.has(path.extname(p)))
    if (source.length === 0) process.exit(0)

    if (uniq.some(p => BANK.some(b => p.endsWith(b)))) process.exit(0)

    const shown = source.slice(0, 5).map(f => `  - ${f}`).join('\n')
    const more = source.length > 5 ? `\n  … and ${source.length - 5} more` : ''
    process.stderr.write(
      `[memory-bank] ${source.length} source file(s) changed this session with no ` +
      `matching update to docs/context/ACTIVE.md or PROGRESS.md:\n${shown}${more}\n` +
      '[REMINDER — not a blocker] If this was meaningful work, record it: what changed in ' +
      'PROGRESS.md, and what is now current/next in ACTIVE.md. The next session re-orients ' +
      'from those two files, so what is missing there is re-derived at full token cost. ' +
      'Skip this only if the change genuinely does not alter project state.\n'
    )
  } catch {
    // Not a git repo, git unavailable, or a timeout: stay silent rather than
    // nagging about something we could not actually determine. Note this also
    // swallows any future bug in the parsing above, degrading to a silent no-op
    // — an accepted cost of the advisory design, not an oversight.
  }
  process.exit(0)
})
