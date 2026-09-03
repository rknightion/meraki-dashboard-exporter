---
id: MDE-0057
title: >-
  Make metric-expiration tracking keys collision-free for delimiter-bearing
  labels
status: To Do
assignee: []
created_date: '2026-09-03 14:43'
labels:
  - 'area:observability'
dependencies: []
priority: medium
type: chore
ordinal: 57000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 3 confirmed a preventive tracking-key collision at the v2.0.0 release tree. src/meraki_dashboard_exporter/core/metric_expiration.py:174-187 builds the tracking and gauge-removal key from _freeze_labels, while lines 216-230 serialize sorted labels as key=value pairs joined by a pipe. Distinct mappings whose label values contain those delimiters can serialize identically; a later update then overwrites timestamp and gauge metadata for the first series, leaving its Prometheus child untracked for TTL and cardinality handling. Current tests use ordinary values only, and no current producer was shown to supply a colliding pair, so this is preventive hardening rather than an observed live collision.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Distinct label mappings cannot collide because of label-value delimiters in the expiration manager internal key
- [ ] #2 Two deliberately colliding legacy encodings remain independently tracked, expired and removed
- [ ] #3 Existing TTL cleanup and cardinality-shedding behavior remains unchanged
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
