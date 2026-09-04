---
id: MDE-0052
title: Validate AnyIO 4.15.0 against cancellation and shutdown contracts
status: In Progress
assignee: []
created_date: '2026-09-03 14:40'
updated_date: '2026-09-04 05:53'
labels:
  - 'area:concurrency'
dependencies: []
priority: medium
type: chore
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The Wave 3 currency pass found AnyIO 4.14.2 locked through the direct runtime requirement at `pyproject.toml:16`, while 4.15.0 is available. Its release changes task-name defaults, lazy imports, cancellation behavior and pytest-plugin handling. Those areas intersect this exporter's bounded admission, request cancellation, lifespan shutdown and async test harness, so the bump was not treated as mechanical despite no declared breaking heading.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 AnyIO 4.15.0 is exercised against request cancellation, lifespan shutdown, managed task groups and the pytest async harness before the lockfile moves
- [ ] #2 Focused async/concurrency tests and the full repository gate pass without weakening timeouts, cancellation assertions or shutdown bounds
- [ ] #3 Behavioral changes found during the bump are documented or split into self-contained follow-up work
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Exercise AnyIO 4.15.0 against cancellation, lifespan shutdown, managed task groups and the async pytest harness; apply only if focused concurrency checks and the full gate pass unchanged.
<!-- SECTION:PLAN:END -->
