---
id: MDE-0017
title: Correct stale repository agent contracts
status: To Do
assignee: []
created_date: '2026-08-23 16:42'
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
- [ ] #1 .github guidance describes the OpenBao broker tokens and never recommends RELEASE_PLEASE_TOKEN or DOCS_SYNC_PAT
- [ ] #2 .github guidance does not claim a removed LLM call site exists
- [ ] #3 docs guidance points to docs.toml and the external site-build ownership model
- [ ] #4 The authoritative source is changed and generated copies are republished rather than hand-edited if these files are generated
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
