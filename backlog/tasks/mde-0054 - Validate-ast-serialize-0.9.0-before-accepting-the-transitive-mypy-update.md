---
id: MDE-0054
title: Validate ast-serialize 0.9.0 before accepting the transitive mypy update
status: In Progress
assignee: []
created_date: '2026-09-03 14:42'
updated_date: '2026-09-04 05:53'
labels:
  - 'area:tooling'
dependencies: []
priority: low
type: chore
ordinal: 54000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The Wave 3 currency pass found uv.lock pinning the transitive mypy dependency ast-serialize 0.8.0 while 0.9.0 is available. Mypy 2.3.1 permits versions below 1.0, but the publisher exposes no usable changelog for 0.9.0, so the update was deliberately deferred instead of treating a minor-version change with unknown behavior as safe. Validate the serialization and cache behavior that this repository exercises before changing the lock.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ast-serialize 0.9.0 release contents and compatibility risk are established from authoritative package artifacts or direct behavior
- [ ] #2 Mypy and repository type-check behavior are compared on 0.8.0 and 0.9.0, including cache creation and reuse
- [ ] #3 The lock update is accepted only if the focused comparison and the full repository gate pass
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Compare ast-serialize 0.8.0 and 0.9.0 release artifacts plus mypy cache creation/reuse and type-check results; update the lock only if compatibility and the full gate pass.
<!-- SECTION:PLAN:END -->
