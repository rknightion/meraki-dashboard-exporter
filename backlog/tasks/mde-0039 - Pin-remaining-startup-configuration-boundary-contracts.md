---
id: MDE-0039
title: Pin remaining startup configuration boundary contracts
status: Done
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-01 22:55'
labels:
  - 'area:tests'
  - 'area:config'
  - needs-triage
dependencies: []
priority: medium
type: task
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found missing or partial boundary coverage for collector timeout equality, server API token normalization, webhook replay and freshness bounds, and collector profile parsing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Tests accept collector timeout equal to per-fetch deadline and reject one second less
- [x] #2 Tests prove blank API tokens normalize to unset and nonblank tokens are trimmed
- [x] #3 Tests cover both valid endpoints and adjacent invalid values for replay, freshness, TTL, and cache-size bounds
- [x] #4 Tests accept the three supported profiles plus unset and reject an invalid profile through real Settings validation
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add compact boundary tests for timeout equality, API-token normalization, webhook bounds, and real collector-profile validation without changing production behavior.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Boundary tests cover timeout equality, trimmed and blank control tokens, both endpoints plus adjacent invalid values for webhook freshness/replay/cache settings, and real validation for unset plus all three supported profiles. Integrated gate: 2827 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Pinned the remaining startup configuration boundaries with compact model and startup tests; just check and just ci pass.
<!-- SECTION:FINAL_SUMMARY:END -->
