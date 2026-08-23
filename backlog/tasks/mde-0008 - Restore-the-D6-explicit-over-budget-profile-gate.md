---
id: MDE-0008
title: Restore the D6 explicit over-budget profile gate
status: To Do
assignee: []
created_date: '2026-08-23 16:42'
labels:
  - 'area:scheduler'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
documentation:
  - backlog doc doc-0004
priority: high
type: bug
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #735 replaced EndpointScheduler.requires_explicit_profile in core/scheduler.py:429 with an unconditional False and made CollectorManager.validate_profile_selection in collectors/manager.py:612 a no-op. That avoids PR #733 P1.5/P2.5-P2.7 crash loops but violates frozen decision D6. Implement the decision coherently: only adaptive mode gates; the threshold is computed from the solved plan versus budget; an implicit over-budget plan refuses startup; an explicit profile is evaluated honestly; and the error names demand, budget, and viable choices. Preserve the full collection surface for an unset profile below the threshold and keep priority 1/2 floors protected.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Adaptive mode refuses an implicit profile only when the computed plan crosses the D6 threshold
- [ ] #2 Fixed mode never applies the adaptive explicit-profile gate
- [ ] #3 Setting a profile is not a no-op remedy: the selected profile is solved and any invalid choice receives an actionable result
- [ ] #4 The pre-yield validation is bounded and cannot create an unbounded inventory warm or a healthy-looking dead background task
- [ ] #5 docs/upgrading.md and scheduler diagnostics describe the implemented D6 behavior
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
