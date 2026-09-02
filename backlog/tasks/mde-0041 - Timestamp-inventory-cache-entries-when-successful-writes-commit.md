---
id: MDE-0041
title: Timestamp inventory cache entries when successful writes commit
status: Done
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-02 07:54'
labels:
  - 'area:inventory'
  - needs-triage
dependencies: []
priority: medium
type: bug
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found inventory cache timestamps captured before lock wait and upstream fetch, then stored after the request. Contention or a slow request can consume the entry TTL before the data is available, causing an immediate refetch.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every inventory cache timestamps a successful write at commit time
- [x] #2 Tests cover lock wait and slow fetch behavior, including the short availability TTL
- [x] #3 Failed fetches do not refresh cache timestamps
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 2 L2: add failing table-driven lock-wait, slow-fetch, and failed-fetch tests first across all six inventory cache families; timestamp only successful cache commits; run focused checks and return evidence without tracker or external writes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 3 reproduced the pre-fetch timestamp pattern across six inventory cache families. A safe correction must update every successful commit path together and prove failures do not refresh timestamps.

Wave 2 red: test_successful_cache_write_timestamp failed for organizations with 100.0 versus the expected 250.0 commit timestamp. All six cache families now timestamp only after successful fetch and assignment. Green: 12 timing regressions, 6 failure regressions, 97 combined inventory tests, typecheck, and just check with 2913 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked after audit. Resume with table-driven lock-wait and slow-fetch regressions for all cache families, then move each timestamp assignment to the successful cache commit.

Wave 2: moved timestamps for all six inventory cache families to successful commit time and added lock-wait, slow-fetch, short-TTL, and failure regressions. Verified by the inventory suite and just check.
<!-- SECTION:FINAL_SUMMARY:END -->
