---
id: MDE-0043
title: Isolate callers from shared network inventory cache records
status: Done
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-01 22:55'
labels:
  - 'area:inventory'
  - needs-triage
dependencies: []
priority: low
type: bug
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found get_networks returns cached dictionaries directly. Collectors append organization fields, permanently enriching the shared raw cache until refresh and exposing caller-owned mutations to unrelated consumers.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every get_networks return path gives callers per-record shallow copies
- [x] #2 Mutating one caller result cannot affect a later inventory read
- [x] #3 NetworkFilter behavior remains unchanged
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add a failing cache-isolation regression, return per-record shallow copies from every get_networks path, and verify NetworkFilter behavior remains unchanged.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The failing regression proved a caller-added orgName persisted into a later cache read. get_networks now shallow-copies each selected record on filtered and unfiltered paths; the full inventory and NetworkFilter suites pass.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Isolated network inventory consumers from shared raw cache dictionaries with test-first mutation coverage; just check and just ci pass.
<!-- SECTION:FINAL_SUMMARY:END -->
