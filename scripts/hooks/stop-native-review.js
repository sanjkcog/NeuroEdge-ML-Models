#!/usr/bin/env node
/**
 * stop-native-review.js
 * Stop hook: if any C++ or C# (.NET) source file was edited this session (per
 * post-edit-native-accumulate.js), require the matching language reviewer —
 * cpp-reviewer for C/C++, csharp-reviewer for C# — before the response ends.
 *
 * This is the C++/C# counterpart to the per-language python-reviewer nudge, and
 * runs IN ADDITION to the holistic stop-code-review-reminder.js pass (design and
 * security concerns the language reviewer is not focused on).
 *
 * Blocking (exit 2), matching stop-code-review-reminder.js: a Stop hook exiting 0
 * only surfaces text in the human transcript, never the agent's own context, so
 * the nudge is missed. Exit 2 feeds stderr back to the agent as required context.
 *
 * The accumulator is cleared unconditionally, so this is a one-shot gate per edit
 * batch: once blocked, the next Stop finds it empty and succeeds. It does not try
 * to detect whether the review actually happened — only that the requirement
 * reached the agent's context once.
 */

'use strict'

const fs = require('fs')
const path = require('path')

const ACCUM_FILE = path.join(process.cwd(), '.claude', '.native-review-files')

// A file's extension decides which reviewer owns it.
const CSHARP_EXT = /\.cs$/i
const CPP_EXT = /\.(cpp|cc|cxx|c\+\+|hpp|hh|hxx|h\+\+|h|c)$/i

let input = ''
process.stdin.on('data', d => (input += d))
process.stdin.on('end', () => {
  process.stdout.write(input)

  if (!fs.existsSync(ACCUM_FILE)) process.exit(0)

  const edited = fs.readFileSync(ACCUM_FILE, 'utf8').split('\n').filter(Boolean)
  fs.writeFileSync(ACCUM_FILE, '')
  if (edited.length === 0) process.exit(0)

  const rel = f => path.relative(process.cwd(), f)
  const cppFiles = edited.filter(f => CPP_EXT.test(f))
  const csFiles = edited.filter(f => CSHARP_EXT.test(f))

  const required = []
  if (cppFiles.length) required.push({ agent: 'cpp-reviewer', lang: 'C/C++', files: cppFiles })
  if (csFiles.length) required.push({ agent: 'csharp-reviewer', lang: 'C#/.NET', files: csFiles })
  if (required.length === 0) process.exit(0)

  for (const r of required) {
    const list = r.files.map(f => `  - ${rel(f)}`).join('\n')
    process.stderr.write(`[${r.agent}] ${r.lang} files edited this session:\n${list}\n`)
  }
  const agents = required.map(r => r.agent).join(' and ')
  process.stderr.write(
    `[REQUIRED ACTION] ${required.length > 1 ? 'C++ and C# source were' : required[0].lang + ' source was'} ` +
    `edited this session and has not been through its language reviewer yet. Before ending this response ` +
    `(or before /prp-commit / /prp-pr), you MUST invoke ${agents} for the file(s) listed above. This is the ` +
    `language-specific pass (idioms, memory/async safety, .NET conventions); it is required in addition to the ` +
    `holistic code-reviewer pass. This is mandatory, not optional. Retrying to end the turn without acting on ` +
    `this defeats the purpose of the gate.\n`
  )
  process.exit(2)
})
