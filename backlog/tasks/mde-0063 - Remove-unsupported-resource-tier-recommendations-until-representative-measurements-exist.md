---
id: MDE-0063
title: >-
  Remove unsupported resource-tier recommendations until representative
  measurements exist
status: To Do
assignee: []
created_date: '2026-09-03 18:46'
labels:
  - 'area:docs'
dependencies:
  - MDE-0002
priority: medium
type: docs
ordinal: 63000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 4 confirmed that the shipped resource-sizing contract still outruns its evidence. charts/meraki-dashboard-exporter/values.yaml:384-412, the chart README and docs/scaling-guide.md:232-255 prescribe small, medium and large CPU and memory quantities. The same guide at lines 257-265 states that the largest actual measurement is a one-network HOMELAB replay, not a medium or dense-switch measurement; the retained fixture has 19 devices. MDE-0002 remains permanently Parked because no reachable organization has the required medium or dense-switch topology. This task must not invent replacement numbers or move defaults: unsupported recommendations should be removed or labeled non-authoritative until representative evidence exists.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every published resource quantity is either the unchanged bootable chart default or is paired with a representative cited measurement and stated assumptions
- [ ] #2 Unsupported medium and large resource recommendations are removed or explicitly marked non-authoritative without replacement estimates
- [ ] #3 Chart values, chart README and scaling guidance use identical evidence labels and retain the measured HOMELAB result as HOMELAB only
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
