---
id: MDE-0041
title: Timestamp inventory cache entries when successful writes commit
status: In Progress
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-02 06:04'
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
- [ ] #1 Every inventory cache timestamps a successful write at commit time
- [ ] #2 Tests cover lock wait and slow fetch behavior, including the short availability TTL
- [ ] #3 Failed fetches do not refresh cache timestamps
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 2 L2: add failing table-driven lock-wait, slow-fetch, and failed-fetch tests first across all six inventory cache families; timestamp only successful cache commits; run focused checks and return evidence without tracker or external writes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 3 reproduced the pre-fetch timestamp pattern across six inventory cache families. A safe correction must update every successful commit path together and prove failures do not refresh timestamps.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked after audit. Resume with table-driven lock-wait and slow-fetch regressions for all cache families, then move each timestamp assignment to the successful cache commit.
<!-- SECTION:FINAL_SUMMARY:END -->
