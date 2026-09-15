# Memory bank — not here

This directory is intentionally almost empty.

Your project's memory bank lives at **`docs/context/`** in your repo root — that is
what the `session-start-memory-bank.js` hook reads and what you maintain:

| File | Holds |
|---|---|
| `docs/context/ACTIVE.md` | current focus + next actions |
| `docs/context/PROGRESS.md` | done / in-progress / blocked |
| `docs/context/REPO_MAP.md` | where things live |
| `docs/context/GLOSSARY.md` | shared vocabulary |
| `docs/context/OPEN_QUESTIONS.md` | unresolved decisions |

Earlier installs copied the AgentForge assets repo's *own* memory bank to this path,
which put a second, foreign, and steadily staler project state beside yours. It was
never read. If you still have those files here from an older install, delete them.
