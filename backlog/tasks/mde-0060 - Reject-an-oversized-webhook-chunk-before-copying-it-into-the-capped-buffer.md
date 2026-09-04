---
id: MDE-0060
title: Reject an oversized webhook chunk before copying it into the capped buffer
status: In Progress
assignee: []
created_date: '2026-09-03 14:43'
updated_date: '2026-09-04 05:53'
labels:
  - 'area:http'
dependencies: []
priority: medium
type: bug
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 2 confirmed a live defensive-resource defect at the v2.0.0 release tree. src/meraki_dashboard_exporter/app.py:1443-1456 extends the request buffer with each complete ASGI chunk before checking the configured maximum. With no trustworthy Content-Length, one chunk much larger than the cap is copied in full before the handler returns 413, so the documented hard application byte cap does not bound the application extra allocation. Existing tests at tests/unit/test_app_webhook_size_cap.py:47-114 use small producer chunks and assert only the response, not bounded accumulation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A chunk larger than the remaining byte budget is rejected before it is copied into the application buffer
- [ ] #2 A focused regression supplies one oversized ASGI chunk and proves the accumulator never grows beyond the configured cap
- [ ] #3 Valid under-cap chunked requests and validation-failure accounting remain unchanged
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Write an oversized single-chunk regression that instruments maximum accumulator size; compare each chunk with remaining capacity before extending while preserving under-cap and validation-failure behavior.
<!-- SECTION:PLAN:END -->
