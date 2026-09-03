---
id: MDE-0049
title: >-
  Expire organization application categories that disappear from the API
  response
status: Done
assignee: []
created_date: '2026-09-03 14:38'
updated_date: '2026-09-03 19:30'
labels:
  - 'area:organization'
dependencies: []
priority: medium
type: bug
ordinal: 49000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 1 confirmed a live stale-series defect at the v2.0.0 release tree. After a successful application-category fetch, `src/meraki_dashboard_exporter/collectors/organization.py:1391-1393` explicitly records no per-series TTL, and `organization.py:1416-1426` writes all four category gauges with direct `.labels().set()` calls. `MetricCollector._set_metric` at `src/meraki_dashboard_exporter/core/collector.py:852-915` is the path that registers series with the expiration manager. If category A is present in one API response and absent in the next, its total, downstream, upstream, and percentage series remain exposed indefinitely with stale values. Existing application-usage tests at `tests/unit/test_organization_collector.py:302-451` and `:452-485` cover one-cycle values and an empty response but do not exercise removal after a prior category.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All four organization application-category gauges are registered for expiration using the ORG_APP_USAGE group TTL
- [x] #2 A failing-before regression proves that a category present in one successful response and absent in a later successful response is removed after its TTL
- [x] #3 Categories that remain present continue to refresh without duplicate or premature removal
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a regression around the real OrganizationCollector application-category path that demonstrates all four category series are not expiration-tracked before the fix and that unchanged categories refresh safely.
2. Route the four writes through `_set_metric` with their enum-backed metric names and the resolved ORG_APP_USAGE TTL; do not change metric names, labels, or endpoint scheduling.
3. Run the focused organization/expiration tests and return the diff to root for integration, full gates, review and finalization.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Test-first evidence: the two-cycle expiration regression failed before the implementation with all four stale category series still untracked; after routing all four writes through _set_metric with the ORG_APP_USAGE TTL, the focused module passed 25 tests. Integrated just check passed 2,939 tests with 5 deselected at 91.25% coverage, and just ci passed the Docker build, seven structure checks, non-root execution, /health and /metrics probes. No metric or label name changed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented in 517f5c8: organization application-category gauges now participate in the existing expiration lifecycle, while categories present in later responses refresh normally. Verified test-first, with focused collector coverage and the complete local source and Docker gates.
<!-- SECTION:FINAL_SUMMARY:END -->
