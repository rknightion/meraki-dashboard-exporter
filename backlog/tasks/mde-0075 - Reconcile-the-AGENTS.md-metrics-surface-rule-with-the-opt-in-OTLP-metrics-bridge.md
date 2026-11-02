---
id: MDE-0075
title: >-
  Reconcile the AGENTS.md metrics-surface rule with the opt-in OTLP metrics
  bridge
status: To Do
assignee: []
created_date: '2026-11-02T16:55:00Z'
labels:
  - needs-triage
  - area:observability
  - priority:medium
dependencies: []
ordinal: 75000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
AGENTS.md (Surfaces and the boundary between them, line 7-9) says Prometheus /metrics is the sole metrics surface and that OpenTelemetry is 'neither ... a metrics mirror'. But src/meraki_dashboard_exporter/core/otel_metrics.py is an opt-in bridge (otel.metrics.enabled, off by default) that pushes snapshots of the Prometheus registry over OTLP (module docstring lines 12-22). An agent following AGENTS.md literally could remove or refuse to extend the bridge; one reading the code could treat AGENTS.md as stale. Found while curating the Groma architecture map. Decide which is intended and make the rule and the code agree.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 AGENTS.md states whether the opt-in OTLP metrics bridge is a sanctioned exception to the sole-metrics-surface rule, and under what conditions
- [ ] #2 If the bridge is not sanctioned, a follow-up task to remove it exists
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
