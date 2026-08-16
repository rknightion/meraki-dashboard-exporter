---
id: MDE-0006
title: Add cloud task environment setup
status: Done
assignee: []
created_date: '2026-08-16 10:28'
updated_date: '2026-08-16 10:43'
labels:
  - 'area:tooling'
dependencies: []
references:
  - 'https://code.claude.com/docs/en/cloud-environments#setup-scripts'
  - 'https://learn.chatgpt.com/docs/environments/cloud-environment#manual-setup'
modified_files:
  - scripts/cloud-environment-setup.sh
priority: high
type: chore
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Provide a repository-owned, idempotent Bash setup script for Codex Cloud and Claude Code cloud environments. It must install the locked Python development environment and the Backlog.md CLI so cloud agents can follow repository instructions, use the task tracker, and execute the full validation workflow. Base the behavior on both products’ setup-script and container-caching models.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A checked-in executable script installs the project Python runtime and all locked development dependencies
- [x] #2 The script installs the Backlog.md CLI at the repository-required version and verifies the backlog command works
- [x] #3 The setup is idempotent and suitable for cached Codex Cloud containers
- [x] #4 Script syntax, tracker access, linting, typing, and tests are validated
- [x] #5 The same checked-in setup command and script support Codex Cloud and Claude Code cloud environment setup fields
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [x] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a fail-fast, cache-safe Bash setup script under scripts/.
2. Bootstrap uv and a user-local pinned Backlog.md CLI, persisting PATH for the separate agent shell.
3. Install Python 3.14 and sync all locked development dependencies.
4. Validate syntax, idempotency, tracker availability, and the project definition-of-done checks.

5. Generalize the script and usage guidance for both Codex Cloud and Claude Code cloud setup fields, then re-run the validation gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added an executable, fail-fast Codex Cloud setup script. It pins uv 0.12.5, Python 3.14.7, and Backlog.md 1.50.1; persists the user-local PATH across the setup/agent shell boundary; syncs all locked development dependencies; and validates tracker and Python access. A second setup run completed without reinstalling pinned tools or rebuilding the environment. `make check` passed: Ruff lint/format, mypy (121 source files), and 2,733 pytest tests.

Follow-up requested: support Claude Code cloud environments as well as Codex Cloud. Claude documents root-run Ubuntu 24.04 Bash setup scripts, a roughly five-minute limit, filesystem snapshot caching, and npm/PyPI access under Trusted networking; the existing provisioning mechanism fits those constraints but its naming and messages are Codex-specific.

Generalized the script name, usage comment, diagnostics, and completion message for Codex Cloud and Claude Code cloud environments. The script remains fail-fast and cache-safe, completes far below Claude Code cloud’s roughly five-minute setup limit, uses only tools and registries available in both hosted images, and persists installed binaries on disk for both cache models. Validation: Bash syntax passed; two consecutive generalized setup runs passed; the isolated transient fleet test passed on retry; and a clean full `make check` rerun passed all 2,733 tests.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Committed b97fe2b: generalized the manual cloud environment setup script for both Codex Cloud and Claude Code cloud setup fields, including platform-neutral naming, instructions, diagnostics, and completion output while retaining pinned Backlog.md and locked development tooling. Verified with Bash syntax, two consecutive setup runs, Backlog.md instruction access, diff checks, an isolated retry of one transient fleet test, and a clean `make check` run with all 2,733 tests passing.
<!-- SECTION:FINAL_SUMMARY:END -->
