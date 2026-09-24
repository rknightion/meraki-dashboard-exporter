---
id: MDE-0072
title: Per-key-throttled endpoint groups spin the collector loop at 1s
status: Done
assignee: []
created_date: '2026-09-24 15:59'
updated_date: '2026-09-24 15:59'
labels:
  - 'area:scheduler'
  - 'priority:high'
dependencies: []
ordinal: 72000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub issue 789. Twelve endpoint groups (MX perf, MX DHCP subnets, MX firewall/security/NAT/VLAN config, MS packet stats, MS STP, MV analytics, MV sense config, clients app usage, clients signal quality) pace fetches with per-serial/per-network timestamps against interval_for and never call should_run. Their scheduler clock stays never-ran (or goes stale 0.9x-interval after a mark_ran from the per-key path), so EndpointScheduler.seconds_until_due returned 0 and app.py::_collector_loop re-ran DeviceCollector every second (max(1.0, 0)). Fix: EndpointGroup.self_paced flag (core/scheduler.py); seconds_until_due skips self-paced groups, which stay solved and stretched; scheduler-owned siblings drive wake-ups.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 seconds_until_due ignores self_paced groups while interval_for still solves them
- [x] #2 Every per-key-throttled DeviceCollector and ClientsCollector group is declared self_paced
- [x] #3 DeviceCollector loop sleeps until its earliest scheduler-owned group is due (regression test)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Regression test tests/unit/test_789_self_paced_endpoint_groups.py reproduced 0.0s wake before the fix, 108s after. just check green, just gen no drift, CodeRabbit clean.
<!-- SECTION:NOTES:END -->
