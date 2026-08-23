---
id: MDE-0019
title: Make endpoint-group success accounting explicit
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
priority: medium
type: bug
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P3.5 remains in core/collector.py:210-255 and scheduler group call sites. At the end of any successful collector cycle, every admitted-but-unmarked group is booked failed. That is correct for swallowed endpoint failures but wrong for benign empty or not-applicable early returns, such as an optional collector with no organizations. Replace inference from absence with an explicit attempted/succeeded/not-applicable/failed verdict that cannot silently turn empty scope into a failure.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Benign empty or not-applicable groups do not increment failure counters
- [ ] #2 Swallowed endpoint failures still increment the correct group failure exactly once
- [ ] #3 Every admitted group finishes a cycle with an explicit verdict
- [ ] #4 Regression tests cover empty scope, partial success, and a real failure
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
