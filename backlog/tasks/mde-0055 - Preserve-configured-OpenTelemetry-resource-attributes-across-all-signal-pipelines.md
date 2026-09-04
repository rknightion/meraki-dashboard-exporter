---
id: MDE-0055
title: >-
  Preserve configured OpenTelemetry resource attributes across all signal
  pipelines
status: Done
assignee: []
created_date: '2026-09-03 14:43'
updated_date: '2026-09-03 19:30'
labels:
  - 'area:observability'
dependencies: []
priority: high
type: bug
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 3 confirmed a live configuration defect at the v2.0.0 release tree. src/meraki_dashboard_exporter/core/config_models.py:681-684 promises additional OpenTelemetry resource attributes, but core/otel_tracing.py:62-69 constructs a resource from four exporter-owned keys and consults the configured mapping only for the legacy environment key. The same builder feeds traces at otel_tracing.py:174, data logs at core/otel_data_logs.py:219, and bridged metrics at core/otel_metrics.py:555. Configuring a nonstandard attribute such as cloud.region or service.namespace therefore silently drops it from every signal, including target_info. Tests use an empty mapping or compare consumers against the same faulty builder, so they do not cover the promised behavior.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every configured OpenTelemetry resource attribute is preserved identically in trace, data-log and metrics-bridge resources
- [x] #2 Exporter-owned service.name, service.version and service.instance.id values remain authoritative when configured attributes collide
- [x] #3 The documented environment compatibility mapping remains supported and is covered alongside a nonstandard attribute
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a failing resource-builder regression with a nonstandard configured attribute, legacy environment mapping and collisions against exporter-owned identity keys. 2. Merge configured attributes before applying exporter-owned identity fields and the resolved deployment environment. 3. Prove trace, data-log and metrics consumers all receive the same resource through focused tests, then return the uncommitted diff to root.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Test-first evidence: the configured nonstandard resource-attribute regression failed before the source change with a missing cloud.region attribute. The implementation merges configured attributes first, translates legacy environment, and then applies authoritative exporter identity fields. Focused cross-signal tests passed, the owned modules passed 70 tests, integrated just check passed 2,939 tests with 5 deselected at 91.25% coverage, and just ci passed all Docker legs. No metric or label name changed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented in 822c6f4: configured OpenTelemetry resource attributes now survive identically into tracing, data logs and bridged metrics while exporter-owned service identity remains authoritative. Verified across all three signal paths and the complete local gates.
<!-- SECTION:FINAL_SUMMARY:END -->
