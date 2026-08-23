---
id: MDE-0015
title: Analyze cardinality from one coherent product-only snapshot
status: Done
assignee: []
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:observability'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: medium
type: bug
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P2.12, P2.13, and P3.8 remain in core/cardinality.py:32-503 and the cardinality drill-down templates. analyze_cardinality walks the live registry twice and infers self_series by subtraction, so concurrent expiration can make a series count negative. _full_metric_data is populated before product/exporter classification, so product-only drill-down pages include runtime and exporter families. The monitor-own family set also retains hardcoded metric literals. Materialize one snapshot, classify every family once, and derive every report and gauge from that population using enums.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 One registry snapshot drives product, exporter, monitor-self, exposed, drill-down, and label results
- [x] #2 The three buckets reconcile exactly and self_series cannot become negative under concurrent mutation
- [x] #3 Product-only drill-down pages exclude exporter, runtime, and CardinalityMonitor families
- [x] #4 CardinalityMonitor metric names use the project metric enums without hardcoded literals
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 1 L4: materialize and classify one registry snapshot, then derive every cardinality view from it; root integrates and finalizes.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented and verified in 7327153. Cardinality analysis now uses one coherent snapshot and enum-owned monitor names; full gates passed.
<!-- SECTION:FINAL_SUMMARY:END -->
