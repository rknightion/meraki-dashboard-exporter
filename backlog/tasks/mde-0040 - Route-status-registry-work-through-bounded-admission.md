---
id: MDE-0040
title: Route status registry work through bounded admission
status: Done
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-02 07:54'
labels:
  - 'area:web'
  - 'area:observability'
  - needs-triage
dependencies: []
priority: high
type: bug
ordinal: 40000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found that building NetworkFilter status iterates the full Prometheus registry synchronously inside the async status route. This bypasses the bounded registry admission introduced for metrics serving and can block health, collection, and shutdown on a large registry.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Status registry work uses the existing bounded registry admission mechanism
- [x] #2 Saturated status requests return the established 503 and Retry-After contract
- [x] #3 Tests cover blocked registry work and cancellation
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 2: add failing status-route concurrency tests first; route status registry collection through the existing bounded registry semaphore and established overload response; verify blocked work and cancellation, then run focused checks before root integration.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 3 located the synchronous registry walk in the async status path. Reusing bounded metrics admission changes a public HTTP overload contract and needs a dedicated design and concurrency test pass.

Wave 2 red: TestStatusEndpointOffload failed because get_network_filter_status was not submitted, saturation returned HTTP 200 rather than 503, and the cancellation test had no offloaded status method. The fix reuses the existing bounded registry slots and serving executor. Green: all three focused tests passed; the six-defect focused suite passed 76 tests; just check passed 2913 tests.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked after audit. Resume by mapping the existing registry-admission helper into both status formats, then test saturation, Retry-After, cancellation, health responsiveness, and shutdown.

Wave 2: routed NetworkFilter status registry collection through the existing bounded serving admission, preserving the established 503 plus Retry-After overload response and holding admission until cancelled worker completion. Verified by offload, saturation, and cancellation regressions plus just check.
<!-- SECTION:FINAL_SUMMARY:END -->
