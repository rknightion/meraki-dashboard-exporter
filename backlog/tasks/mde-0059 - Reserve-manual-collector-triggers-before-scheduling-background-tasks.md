---
id: MDE-0059
title: Reserve manual collector triggers before scheduling background tasks
status: In Progress
assignee: []
created_date: '2026-09-03 14:43'
updated_date: '2026-09-04 05:53'
labels:
  - 'area:http'
dependencies: []
priority: medium
type: bug
ordinal: 59000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 2 confirmed a live admission race at the v2.0.0 release tree. src/meraki_dashboard_exporter/app.py:1350-1363 checks CollectorManager.is_collector_running and then creates a background task. asyncio.create_task does not start the coroutine before the handler returns, so concurrent authenticated requests can all pass the check, each return started, and accumulate one task per request. CollectorManager later suppresses duplicate execution at collectors/manager.py:819-839, but only after those tasks begin. Existing endpoint tests cover the already-running state and a single mocked task, not concurrent real requests or task cleanup.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A synchronous per-collector reservation is installed before a manual trigger response reports started
- [ ] #2 Concurrent authenticated triggers for one inactive collector schedule exactly one run and every duplicate reports running
- [ ] #3 The reservation and retained background task are cleared after completion, cancellation and failure
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Write a real concurrent authenticated-trigger regression plus completion, cancellation and failure cleanup coverage; install a synchronous per-collector reservation before task creation and clear it on every terminal path.
<!-- SECTION:PLAN:END -->
