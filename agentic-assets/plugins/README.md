# Plugins (MCP Servers)

External integrations via Model Context Protocol. Enable max ~10 at a time to preserve context window.

`mcp-servers.json` is a catalog of commonly useful MCP servers. To activate one, copy its entry
into the `mcpServers` section of your `~/.claude.json` and fill in any `YOUR_*_HERE` placeholders.

| Category | Servers |
|---|---|
| Core dev | github, memory, sequential-thinking, filesystem |
| Testing | playwright, browserbase |
| Search | exa-web-search, context7 |
| Cloud | vercel, railway, cloudflare-* |
| Data | supabase, clickhouse |
| AI | fal-ai, evalview |
| Project management | jira, confluence |
| Orchestration | devfleet |

## Legacy Project Profile

For brownfield onboarding, use `legacy-project-onboarding.json` as the recommended plugin/MCP profile. It points Claude to:

- `/legacy-audit` as the default command.
- `legacy-modernizer` as the primary agent.
- `legacy-modernization` as the primary skill.
- `filesystem`, `github`, `memory`, `context7`, `playwright`, and optional `devfleet` as the MCP set.

Keep the active MCP set small. Start with `filesystem`, `github`, and `memory`; add `context7` only when library documentation is needed, `playwright` only for UI validation, and `devfleet` only for large subsystem mapping.
