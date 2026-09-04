---
id: MDE-0051
title: Validate the Meraki SDK 4.5.0 generated API upgrade
status: Done
assignee: []
created_date: '2026-09-03 14:40'
updated_date: '2026-09-04 06:38'
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
- [x] #1 The 4.5.0 generated operation surface is diffed against every SDK method the exporter calls, with changed signatures and response shapes dispositioned
- [x] #2 The exact pyproject and lockfile pins move together only after focused collector/API facade and offline conformance tests pass
- [x] #3 Any changed endpoint contract is documented or split into a self-contained follow-up rather than hidden by mock changes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Diff Meraki SDK 4.5.0 against every exporter-used operation, validate changed signatures and shapes, then apply the exact pin only if focused facade/collector/conformance checks and the full gate pass.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Accepted Meraki SDK 4.5.0 in c3c65d2. Static extraction found 109 exporter-used SDK operations; all exist in 4.5.0, their signatures and generated implementations match 4.4.0, and relevant OpenAPI 1.73.0 to 1.74.0 changes do not affect exporter usage. An isolated 206-test suite and an applied-checkout 210-test API, facade, model, transport, and conformance slice passed; just check passed 2,958 selected tests at 91.49% coverage. Updated the editable API and core instruction files. The generated root AGENTS.md still names 4.4.0 and was not hand-edited across its policy-source ownership boundary; its own sentence directs readers to pyproject.toml for current truth.
<!-- SECTION:FINAL_SUMMARY:END -->
