---
id: MDE-0031
title: Preserve Meraki credentials across legitimate shard redirects
status: Done
assignee: []
created_date: '2026-09-01 21:56'
updated_date: '2026-09-01 22:55'
labels:
  - 'area:api'
  - 'priority:high'
dependencies: []
priority: high
type: bug
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Release review finding P1.2 remains live at src/meraki_dashboard_exporter/api/client.py:42-51. Redirect authentication is currently preserved only for the configured origin, so legitimate Meraki shard or regional hosts can lose Authorization and enter a persistent 401 path. The redirect boundary must preserve credentials only for documented Meraki-owned host suffixes while stripping them for attacker-controlled lookalikes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A legitimate Meraki shard or regional redirect retains the Authorization header
- [x] #2 A lookalike host such as a Meraki name under an attacker-controlled parent domain loses the Authorization header
- [x] #3 Tests cover legitimate shard, attacker-controlled lookalike, and existing same-origin behavior
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement the host-boundary redirect credential policy in the existing API client with failing tests for legitimate Meraki shards and attacker-controlled lookalikes, then run the focused API tests.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Test-first redirect coverage now preserves Authorization only between configured or Meraki-owned HTTPS origins and strips it for attacker-controlled lookalikes. Integrated gate: 2827 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented a suffix-boundary Meraki redirect trust policy with regional/shard, lookalike, and same-origin tests; just check and just ci pass.
<!-- SECTION:FINAL_SUMMARY:END -->
