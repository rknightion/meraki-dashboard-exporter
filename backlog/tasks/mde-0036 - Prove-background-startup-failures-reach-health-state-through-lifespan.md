---
id: MDE-0036
title: Prove background startup failures reach health state through lifespan
status: Done
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-01 22:55'
labels:
  - 'area:tests'
  - needs-triage
dependencies: []
priority: high
type: bug
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found no test that drives the lifespan-created startup task through _on_startup_task_done after collect_initial raises StartupConfigurationError. A callback regression could leave health green while startup collection has failed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A lifespan-driven test lets the background startup task settle after StartupConfigurationError
- [x] #2 The test proves the startup configuration error is retained and health returns 503
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Exercise the real lifespan-created startup task with a delayed StartupConfigurationError and assert the callback records it for the health endpoint.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
A real lifespan test now lets the background startup task fail after yield, proves the callback retains StartupConfigurationError, proves the dead-man switch trips, and verifies GET /health returns 503. Integrated gate: 2827 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added the missing lifespan/background-task health contract; post-yield startup configuration failure is proven to return HTTP 503.
<!-- SECTION:FINAL_SUMMARY:END -->
