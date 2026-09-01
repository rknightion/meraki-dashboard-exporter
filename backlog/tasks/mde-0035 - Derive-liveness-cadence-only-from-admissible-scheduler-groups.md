---
id: MDE-0035
title: Derive liveness cadence only from admissible scheduler groups
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
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found that fastest_effective_interval_seconds includes profile-excluded and shed groups. Under the availability profile, an excluded faster group can make the process fail liveness before its only admissible group is due.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The fastest interval considers only enabled, profile-allowed, non-shed groups
- [x] #2 An empty admissible set falls back to the configured resolve interval
- [x] #3 A regression test covers the availability-profile 180-second versus 270-second boundary
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add the availability-profile liveness regression, filter the fastest cadence to admissible non-shed groups, and run focused scheduler and liveness tests.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The failing availability-profile regression observed 60 seconds from an excluded priority-2 group instead of 300 seconds from the admissible priority-1 group. The liveness cadence now uses enabled/profile-allowed/non-shed groups and falls back when none exist. Integrated gate: 2827 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Made liveness cadence profile-aware and shed-aware with a test-first availability-profile regression; just check and just ci pass.
<!-- SECTION:FINAL_SUMMARY:END -->
