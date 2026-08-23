---
id: MDE-0017
title: Correct stale repository agent contracts
status: Done
assignee: []
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:docs'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: medium
type: docs
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P2.15 remains current. .github/CLAUDE.md still claims release-please and docs sync use revoked PATs and describes a removed Claude action; docs/CLAUDE.md still tells agents to edit ignored zensical.toml even though docs.toml and the external hub own navigation. Rewrite both generated instruction sources through their authoritative policy source if applicable, not only the checked-in generated copies, so following the contract cannot restore a revoked credential or silently omit navigation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 .github guidance describes the OpenBao broker tokens and never recommends RELEASE_PLEASE_TOKEN or DOCS_SYNC_PAT
- [x] #2 .github guidance does not claim a removed LLM call site exists
- [x] #3 docs guidance points to docs.toml and the external site-build ownership model
- [x] #4 The authoritative source is changed and generated copies are republished rather than hand-edited if these files are generated
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Replacement lane L14: identify the authoritative source of each repository agent contract, update that source, then republish the generated .github/CLAUDE.md and docs/CLAUDE.md copies. Do not hand-edit generated copies without source ownership proof.

Authoritative-source check resolved: these nested CLAUDE.md files are ordinary repository-owned tracked contracts, not generated copies. Edit them directly to match already-landed workflow and docs.toml state; validate claims against the actual workflows and manifest.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Preflight found no generator, policy-source reference, or generated-file banner for these nested CLAUDE.md files. Git history shows they are repository-authored tracked files; the task conditional therefore resolves to editing the checked-in contracts directly. docs.toml already exists and zensical.toml is absent, confirming the stale documentation claim.

Mid-run ownership preflight: no other agent or human owns .github/CLAUDE.md or docs/CLAUDE.md. Root Backlog writes and other lane source files are fenced; explicit staging only.

Launch message: concurrent work is fenced to the task-owned .github/CLAUDE.md and docs/CLAUDE.md; do not use git add -A or git commit -a. Root retains Backlog and all commit ownership.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Repository-authored nested agent contracts were corrected in 7327153. These files have no generator or upstream policy source; full gates passed.
<!-- SECTION:FINAL_SUMMARY:END -->
