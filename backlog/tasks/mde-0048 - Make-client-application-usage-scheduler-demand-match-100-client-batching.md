---
id: MDE-0048
title: Make client application-usage scheduler demand match 100-client batching
status: To Do
assignee: []
created_date: '2026-09-03 14:38'
labels:
  - 'area:scheduler'
dependencies: []
priority: high
type: bug
ordinal: 48000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 1 confirmed a live scheduler-accounting defect at the v2.0.0 release tree. `src/meraki_dashboard_exporter/collectors/clients.py:60-64` budgets `CLIENTS_APP_USAGE` as one request per network, while `clients.py:1255-1273` splits emitted client IDs into batches of 100 and makes one `getNetworkClientsApplicationUsage` request per batch. A network with 150 emitted clients is therefore costed as one request but performs two; at the configured 10,000-client cap it can perform 100. The adaptive solver can leave the group unstretched on understated demand and push avoidable load into 429 handling. `tests/unit/test_clients_collector.py:923-950` proves the multi-call behavior, while `tests/unit/test_clients_scheduler_gates.py:83-90` pins the incorrect one-call estimate. The implementation needs an explicit product choice between exact observed-client demand and a conservative bounded estimate; the current `OrgShape` has no client-count field.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The declared CLIENTS_APP_USAGE demand cannot understate the number of 100-client API batches the collector can emit for a network
- [ ] #2 A 150-client regression reconciles the scheduler demand with the two requests exercised by the existing batching test
- [ ] #3 The chosen observed-count or conservative-bound policy is documented with its source, cap, and overestimation trade-off
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
