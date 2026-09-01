---
id: MDE-0034
title: Reject non-positive adaptive scheduler interval overrides
status: Done
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-01 22:55'
labels:
  - 'area:scheduler'
  - needs-triage
dependencies: []
priority: high
type: bug
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found that SchedulerSettings accepts group interval overrides of zero or less. core/scheduler.py then divides by zero or records negative demand, which can crash startup or conceal an over-budget plan.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Configuration rejects every group interval override less than or equal to zero with an actionable validation error
- [x] #2 The interval solver also rejects non-positive programmatic overrides before demand arithmetic
- [x] #3 Tests cover zero, negative, and valid positive overrides
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add failing configuration and solver tests for zero and negative overrides, then reject non-positive values at both boundaries and run the focused scheduler suite.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Failing tests observed ZeroDivisionError for zero and silent negative demand for minus one before the fix. Pydantic now rejects both, and the pure solver fails closed for programmatic callers. Integrated gate: 2827 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Rejected non-positive group interval overrides at configuration and solver boundaries with test-first zero/negative coverage; just check and just ci pass.
<!-- SECTION:FINAL_SUMMARY:END -->
