---
id: MDE-0009
title: Give collector admission one honest wall-clock budget
status: To Do
assignee: []
created_date: '2026-08-23 16:42'
labels:
  - 'area:scheduler'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: high
type: bug
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P1.6 and P2.8 remain in collectors/manager.py:800-965. Admission can wait collector_timeout and execution can then consume collector_timeout again, while TaskExpiredBeforeStartError increments collector failure_streak and total_failures even though it proves exporter saturation rather than collector health. Keep the derived-capacity warning required by D10, but make one run use one wall-clock budget and separate admission-pressure accounting from endpoint health. Coordinate with MDE-0001 because both inspect collector admission and duration evidence.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Admission plus execution cannot exceed one configured wall-clock budget except bounded cancellation cleanup
- [ ] #2 Admission expiry is observable as exporter saturation without incrementing the collector endpoint failure streak
- [ ] #3 A concurrent regression test exercises queue expiry and proves the collector body did not start
- [ ] #4 Utilization and health reporting distinguish queue wait from execution time
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
