---
id: MDE-0014
title: Make facade retry timing and request metrics truthful
status: Done
assignee: []
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:api'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: medium
type: bug
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #735 restored jitter but PR #733 P2.2/P3.2 remain in core/api_facade.py:80-140 and api/client.py:155-190. No-Retry-After backoff starts at one second instead of the previous ten-second base, the compatibility retry counter is never incremented by facade-owned retries, method is permanently unknown, and non-HTTP exceptions occupy the status_code label. Define one retry policy and metric contract that reflects actual attempts without pretending exception classes are HTTP codes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Facade retries use a documented jittered base and honor bounded Retry-After values
- [x] #2 Every retry increments the compatibility retry-attempt counter exactly once
- [x] #3 HTTP status labels contain HTTP status values only, with non-HTTP outcomes represented separately
- [x] #4 Grafana queries and generated metric docs are updated if the label contract changes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 1 L2: define the retry and request-attempt metric contract alongside MDE-0013 in the single-owned API facade seam; root integrates and finalizes.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented and verified in 7327153. Retry timing and attempt/status metrics are truthful; generated docs passed and existing Grafana status_code queries remain structurally valid.
<!-- SECTION:FINAL_SUMMARY:END -->
