---
id: MDE-0023
title: Derive Helm shutdown validation from the config schema
status: Done
assignee: []
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:deploy'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: low
type: bug
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P3.15 remains in charts/meraki-dashboard-exporter/templates/_validation.tpl:19-29. The validation hardcodes default 120 outside generated markers, duplicating APISettings.per_fetch_deadline_seconds. A schema default change can therefore render a termination grace shorter than the application fetch deadline. Generate or otherwise single-source the Helm fallback and add render tests for default and overridden values.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The chart shutdown-grace validator has no independently hardcoded copy of the API deadline default
- [x] #2 A schema default change propagates to the rendered validation contract through make docgen
- [x] #3 Helm tests cover the default, a valid override, an invalid override, and forbidden extraEnv bypass
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
- Generate the Helm shutdown validator fallback from the schema-derived API deadline knob.
- Pin default, override, rejection, and forbidden extraEnv behavior with Helm render tests; root runs shared gates and finalizes.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented and verified in 7327153. Helm shutdown validation is schema-derived and covered by render tests; full gates passed.
<!-- SECTION:FINAL_SUMMARY:END -->
