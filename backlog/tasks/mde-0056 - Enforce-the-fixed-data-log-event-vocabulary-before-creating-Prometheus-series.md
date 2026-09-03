---
id: MDE-0056
title: Enforce the fixed data-log event vocabulary before creating Prometheus series
status: To Do
assignee: []
created_date: '2026-09-03 14:43'
labels:
  - 'area:observability'
dependencies: []
priority: medium
type: chore
ordinal: 56000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 3 confirmed a preventive cardinality gap at the v2.0.0 release tree. src/meraki_dashboard_exporter/core/otel_data_logs.py:81 defines BUILT_IN_EVENTS from DataLogEvent, but is_event_enabled at lines 301-305 checks only global enablement and the configured allowlist. emit at lines 335-370 then uses any supplied string as the event.name attribute and as the event label on the emitted/dropped Prometheus counters. All current producers use enum members, so this is preventive rather than a present unbounded producer; however, a future API-derived name or typo explicitly allowlisted can create one self-observability series per value despite the documented fixed vocabulary. Existing tests even allow some.other.event and do not assert rejection of unknown emitted values.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Names outside BUILT_IN_EVENTS are rejected before an OTLP record, status entry or Prometheus counter series is created
- [ ] #2 Every DataLogEvent value remains enabled under the default configuration and when explicitly allowlisted
- [ ] #3 The bounded event-label contract is stated at the validation point and covered by focused tests
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
