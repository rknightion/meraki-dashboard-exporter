---
id: MDE-0067
title: Make the startup collector summary honest about disabled collectors
status: To Do
assignee: []
created_date: '2026-09-04 07:27'
labels:
  - 'area:observability'
  - needs-triage
dependencies: []
priority: medium
type: bug
ordinal: 67000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Verified live on the shipped v2.0.1 build. With an operator explicitly setting COLLECT_INSIGHT=false, the startup banner logs that setting as a warning line and then two lines later reports skipped_collectors: 0, lists insight in both configured_names and 'Enabled Collectors', prints a cadence for it under 'Collector Cadences', and starts a per-collector loop task for it (task_count 9). Reading the startup logs, an operator concludes the collector is on.

The runtime behaviour is correct: collectors/insight.py:178 returns an empty endpoint-group tuple and collectors/insight.py:277 returns early, so no API call is made and no error series appears. The disagreement is between the log summary and reality, and it is the same shape as MDE-0065/MDE-0066 - a top-level surface reporting health that the internals contradict.

The mechanism is that the collector-level is_active property (core/collector.py:79, overridden at collectors/insight.py:189 and collectors/clients.py:128) is already the intended signal and is consulted by the web UI (app.py:1125) and the manual-trigger control API (app.py:1441), but not by the startup summary in app.py:1161-1190 or by the manager's registration and loop-start path in collectors/manager.py:262-330. collectors.active_collectors is a separate setting from the per-collector collect_* flags, so a collector switched off through its own flag is never added to skipped_collectors.

Scope is the log summary and the no-op loop, not the collector gating, which already works.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The startup collector summary counts a collector disabled by its own collect_* flag as skipped, with the flag named as the reason, rather than reporting it enabled
- [ ] #2 'Enabled Collectors' and the printed cadences exclude a collector whose is_active is false
- [ ] #3 No per-collector loop task is started for a collector whose is_active is false
- [ ] #4 A regression covers a disabled-by-flag collector and asserts the summary, the enabled list and the started task set all agree with is_active
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
