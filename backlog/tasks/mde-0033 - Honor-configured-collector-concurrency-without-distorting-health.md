---
id: MDE-0033
title: Honor configured collector concurrency without distorting health
status: Done
assignee: []
created_date: '2026-09-01 21:56'
updated_date: '2026-09-01 22:55'
labels:
  - 'area:concurrency'
  - 'priority:high'
dependencies: []
priority: high
type: bug
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Release review finding P1.6 remains live at src/meraki_dashboard_exporter/collectors/manager.py:38-49. Shipped defaults configure five concurrent collectors but derive an effective limit of two from the serving executor, while admission expiry can consume the collector timeout and risks being confused with collector health. The effective concurrency contract must be explicit, capacity-safe, and keep queue pressure separate from endpoint failure accounting.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Shipped defaults produce the intended documented effective collector concurrency
- [x] #2 Any unavoidable cap reports configured limit, executor workers, fan-out allowance, and effective limit
- [x] #3 TaskExpiredBeforeStartError does not increment collector failure streak or endpoint-group failure counters
- [x] #4 Tests pin the default limit and admission-expiry health behavior, and operator documentation matches
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Root-owned manager seam shared with MDE-0032: make shipped effective collector concurrency intentional and keep admission expiry separate from health, with targeted concurrent tests and operator docs.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Shipped defaults intentionally admit two collectors from executor workers 10 divided by per-collector fan-out 5; warning diagnostics name every input, and admission expiry remains separate from health accounting. Generated config docs were refreshed. Integrated gate: 2827 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Made the effective collector-concurrency contract explicit, pinned shipped defaults and admission-expiry health behavior, and regenerated operator documentation; just check and just ci pass.
<!-- SECTION:FINAL_SUMMARY:END -->
