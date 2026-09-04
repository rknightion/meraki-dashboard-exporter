---
id: MDE-0051
title: Validate the Meraki SDK 4.5.0 generated API upgrade
status: In Progress
assignee: []
created_date: '2026-09-03 14:40'
updated_date: '2026-09-04 05:53'
labels:
  - 'area:api'
dependencies: []
priority: medium
type: chore
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The Wave 3 currency pass found the exact runtime pin `meraki==4.4.0` at `pyproject.toml:21` and `uv.lock` while 4.5.0 is available. The 4.5.0 release regenerates the SDK from Meraki OpenAPI 1.74.0 instead of 1.73.0 and declares no breaking entry, but generated method signatures and response shapes can move even without a hand-written breaking changelog. This was not included in the safe batch because collectors depend on exact operation names, pagination kwargs and nullable response contracts.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The 4.5.0 generated operation surface is diffed against every SDK method the exporter calls, with changed signatures and response shapes dispositioned
- [ ] #2 The exact pyproject and lockfile pins move together only after focused collector/API facade and offline conformance tests pass
- [ ] #3 Any changed endpoint contract is documented or split into a self-contained follow-up rather than hidden by mock changes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Diff Meraki SDK 4.5.0 against every exporter-used operation, validate changed signatures and shapes, then apply the exact pin only if focused facade/collector/conformance checks and the full gate pass.
<!-- SECTION:PLAN:END -->
