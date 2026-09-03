---
id: MDE-0064
title: Reconcile Helm agent instructions with the post-v2 chart contracts
status: To Do
assignee: []
created_date: '2026-09-03 19:43'
labels:
  - 'area:helm'
  - needs-triage
dependencies: []
priority: medium
type: docs
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The Wave 5 fallback reconciliation found two stale operational claims in charts/meraki-dashboard-exporter/CLAUDE.md. Lines 106-107 say NetworkPolicy emits OTLP egress only when config.otelEnabled is true, but MDE-0061 changed templates/networkpolicy.yaml so any enabled tracing, logs, or metrics channel emits the shared chart OTLP port; distinct ports remain an explicit extraEgress responsibility. Lines 74-76 still call the 256Mi/512Mi default SMALL-scale-only and direct agents to scale-tier comments whose recommendations MDE-0063 confirmed are unsupported by representative measurements. A future agent following either claim can regress logs-only or metrics-only egress, or restore unsourced resource recommendations. Reconcile the instruction text with the landed chart and MDE-0063 without inventing sizing figures.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The NetworkPolicy instruction states that any enabled tracing, logs, or metrics channel emits the shared chart OTLP port and explains the existing extraEgress route for distinct ports
- [ ] #2 The resource-sizing instruction no longer endorses unsupported scale-tier quantities and points to the representative-measurement contract tracked by MDE-0063 without adding a new estimate
- [ ] #3 All other claims in the touched Helm instruction paragraphs are checked against the current templates and values before the task is finalized
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
