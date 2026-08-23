---
id: MDE-0022
title: Lock the API-drift environment and remove the dead site dependency
status: Done
assignee: []
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:ci'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: low
type: chore
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P3.13/P3.14 remain in .github/workflows/api-drift.yml:34 and pyproject.toml:48. The scheduled drift workflow is the only uv sync without --locked, so conformance may run against dependencies different from CI. The repository no longer builds the Zensical site locally, but zensical remains a direct dependency and lockfile surface. Make the drift environment reproducible and remove the package only after confirming no local script or test imports it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 API drift installs with uv sync --locked
- [x] #2 No repository-owned runtime, script, test, or Make target requires zensical
- [x] #3 pyproject.toml and uv.lock no longer carry the dead direct dependency
- [x] #4 The drift workflow and dependency metadata validate cleanly
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 1 L7: lock API drift dependency sync and remove zensical only after proving it unused; root integrates and finalizes.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented and verified in 7327153. API drift uses the locked environment and the dead direct Zensical dependency was removed; full gates passed.
<!-- SECTION:FINAL_SUMMARY:END -->
