# Give these to NeuroEdge

Files this run produces for the portal. Each one is a **copy** — the original stays where the tools
read it, and `handoff.json` records the source and its hash, so a stale copy here is detectable
(`handoff verify`).

They are numbered in **upload order**, not by milestone. Upload one, paste the registration id or
the refusal back with `handoff sent`, and it moves to `sent/`.

Run `/agentforge-ml handoff` to see what is outstanding for this project's runner, and where each
file goes in the portal.

What comes back the other way goes in `../from-neuroedge/`.
