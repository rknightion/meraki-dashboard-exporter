---
id: MDE-0038
title: Verify every production API facade owner resolves a limiter
status: In Progress
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-02 06:04'
labels:
  - 'area:tests'
  - 'area:api'
  - needs-triage
dependencies: []
priority: medium
type: bug
ordinal: 38000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found that limiter resolution is tested only with an artificial parent chain. A production collector or subcollector can lose parent or limiter wiring and fail only on its first live API call.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The test inventory discovers every production facade_for owner
- [ ] #2 Each production ownership chain resolves a non-null limiter before a live API call
- [ ] #3 Any deliberate exception is enumerated and justified in the test
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 2 L4 phase 2 after MDE-0037: add a failing production facade-owner inventory test, construct each owner family, prove every non-exempt ownership chain resolves a limiter, enumerate justified exceptions, and run focused checks.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 3 established that the current contract test covers only an artificial owner chain. Enumerating and constructing every production owner needs a dedicated mapping pass.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked after audit. Resume by generating a complete facade_for owner inventory, defining construction fixtures for each owner family, and proving every non-exempt chain resolves a limiter.
<!-- SECTION:FINAL_SUMMARY:END -->
