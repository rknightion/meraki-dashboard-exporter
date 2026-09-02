---
id: MDE-0044
title: Make DNS cache clear linearizable with in-flight resolution
status: In Progress
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-02 06:04'
labels:
  - 'area:dns'
  - needs-triage
dependencies: []
priority: low
type: bug
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found clear_cache resets cache and counters while in-flight resolver work can later repopulate entries and publish pre-clear backlog state. The authenticated clear operation therefore does not define a reliable generation boundary.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Resolution work begun before a clear cannot publish cache entries or queue metrics into the post-clear generation
- [ ] #2 A regression test blocks a lookup across clear and proves cache contents and counters remain cleared
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 2 L3: add a failing blocked-lookup-across-clear test first; capture a generation token per resolution batch and reject cache and metric publication after a clear; run focused checks and return evidence without tracker or external writes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 3 reproduced the generation race between clear_cache and in-flight resolution. The fix is a concurrency contract, not a local field update.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked after audit. Resume by adding a cache generation token captured by each batch and rejecting pre-clear publications, with a blocked-lookup regression for cache and queue metrics.
<!-- SECTION:FINAL_SUMMARY:END -->
