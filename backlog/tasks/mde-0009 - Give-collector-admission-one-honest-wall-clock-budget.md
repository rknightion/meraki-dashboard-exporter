---
id: MDE-0009
title: Give collector admission one honest wall-clock budget
status: Done
assignee:
  - '@codex'
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 17:29'
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
- [x] #1 Admission plus execution cannot exceed one configured wall-clock budget except bounded cancellation cleanup
- [x] #2 Admission expiry is observable as exporter saturation without incrementing the collector endpoint failure streak
- [x] #3 A concurrent regression test exercises queue expiry and proves the collector body did not start
- [x] #4 Utilization and health reporting distinguish queue wait from execution time
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [x] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add concurrent failing tests proving queue expiry never starts the collector or mutates endpoint health, and queue wait plus execution share one monotonic deadline. 2. Pass the remaining run budget from admission into execution, retain task-admission saturation metrics, and remove pre-start failure accounting from collector health while clarifying utilization semantics. 3. Run focused concurrency/utilization tests, regenerate metric docs if help text changes, then CodeRabbit and make check before finalizing.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented one monotonic collector-run deadline across admission and execution in 223b5f2. Admission expiry now remains visible through shared saturation metrics without mutating collector endpoint health; execution utilization excludes queue wait. Concurrent regressions prove an expired queued body never starts and that queue wait plus execution stop at the original deadline. Verified with focused admission/concurrency/utilization/tracing tests, make docgen, a clean CodeRabbit re-review (0 findings), and make check (Ruff, format, mypy, 2,744 tests passed). No metric or label names changed, so Grafana query updates were not applicable.
<!-- SECTION:FINAL_SUMMARY:END -->
