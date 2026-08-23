---
id: MDE-0012
title: Separate API-usage overview success from enrichment success
status: To Do
assignee: []
created_date: '2026-08-23 16:42'
labels:
  - 'area:organization'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: medium
type: bug
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P2.10 remains in collectors/organization_collectors/api_usage.py:215-350. The primary overview can emit fresh status-code metrics while an optional multi-page operation enrichment leaves ORG_API_USAGE unmarked, causing a permanent stale alert and failure-retry cadence. Give the enrichment its own endpoint-group verdict or an explicit partial-success model so the scheduler and alerts describe each surface honestly.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Primary overview success refreshes the success signal used by its metrics and alert
- [ ] #2 Enrichment failure is separately observable and does not force the overview onto failure retry cadence
- [ ] #3 A regression test covers successful overview plus timed-out enrichment
- [ ] #4 Endpoint cost and cadence remain represented in the scheduler model
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
