---
id: MDE-0061
title: >-
  Support independent OTLP logs and metrics channels in Helm validation and
  egress
status: Done
assignee: []
created_date: '2026-09-03 18:46'
updated_date: '2026-09-03 19:30'
labels:
  - 'area:helm'
dependencies: []
priority: high
type: bug
ordinal: 61000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 4 confirmed a high live deployment defect at the v2.0.0 release tree. core/config_models.py:534-615 and 718-738 make tracing, data logs and bridged metrics independent channels with endpoint inheritance. Helm emits all three channel settings in charts/meraki-dashboard-exporter/templates/configmap.yaml:156-205, but templates/_validation.tpl:34-44 validates only tracing, and templates/networkpolicy.yaml:49-58 opens the configured OTLP egress port only when tracing is enabled. A logs-only or metrics-only chart can render without any endpoint and then fail application startup; with NetworkPolicy enabled, a valid logs-only or metrics-only deployment can omit the collector port and block export. Focused helm renders reproduced both states, while existing chart tests cover generated mapping and shutdown validation only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Helm rendering rejects each enabled tracing, logs or metrics channel when neither its own endpoint nor the shared endpoint resolves
- [x] #2 The configured OTLP NetworkPolicy egress port is emitted when any tracing, logs or metrics channel is enabled
- [x] #3 Focused renders cover tracing-only, logs-only, metrics-only, inherited endpoints and independent endpoints without changing application endpoint semantics
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add failing Helm-render regressions for logs-only and metrics-only missing endpoints and missing NetworkPolicy OTLP egress. 2. Mirror application endpoint inheritance for all three channels in Helm validation. 3. Treat networkPolicy.egress.otlpPort as the chart-wide OTLP port and emit it when any channel is enabled; distinct channel ports remain available through the existing extraEgress escape hatch. 4. Run focused chart tests and return the uncommitted diff to root.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Validation-first evidence: before the templates changed, focused Helm renders had 4 failures out of 10 because logs-only and metrics-only missing endpoints rendered and their NetworkPolicies omitted port 4317. After the fix, all 10 focused renders passed and helm lint reported 1 chart linted, 0 failed. Integrated just check passed 2,939 tests with 5 deselected at 91.25% coverage, and just ci passed all Docker legs. Distinct channel ports remain available through existing extraEgress; no application endpoint, metric or label semantics changed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented in 31c1d25: Helm now mirrors application endpoint inheritance for each independent OTLP signal and opens the declared OTLP egress port whenever any signal is enabled. Verified through tracing-only, logs-only, metrics-only, inherited and independent endpoint renders.
<!-- SECTION:FINAL_SUMMARY:END -->
