# meraki-dashboard-exporter

Contributor and agent instructions live in `AGENTS.md`, which Claude Code and Codex both read.
One canonical file means the two cannot drift apart.

Until 2026-08-14 this repo achieved that with a symlink (`AGENTS.md -> CLAUDE.md`). The import is
the standard arrangement across Rob's repos, so it replaced the symlink when the tracker moved to
Backlog.md. Edit `AGENTS.md`; never re-fork the content back into here.

The 16 per-directory `CLAUDE.md` files under `src/`, `docs/`, `grafana/`, `scripts/`, `tests/`,
`charts/`, `tools/` and `.github/`, together with this root file, are the 17 in-repository
instruction files and remain the detailed context for those trees.
Note that Codex does not read them — anything an agent must know regardless of harness belongs in
`AGENTS.md`.

@AGENTS.md
