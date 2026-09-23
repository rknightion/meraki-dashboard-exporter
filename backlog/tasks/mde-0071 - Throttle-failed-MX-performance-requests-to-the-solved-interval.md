---
id: MDE-0071
title: Throttle failed MX performance requests to the solved interval
status: Done
assignee: []
created_date: '2026-09-23 19:00'
updated_date: '2026-09-23 19:06'
labels:
  - 'area:collectors'
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/issues/785'
priority: high
type: bug
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub issue #785 reports that getDeviceAppliancePerformance raises a 400 Feature not supported for an MX without score support. In src/meraki_dashboard_exporter/collectors/devices/mx.py the per-serial timestamp is recorded only after the fetch, so the next device collection cycle retries immediately, flooding logs and spending API budget.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A failed MX performance request is attempted at most once per solved mx_performance interval per serial
- [x] #2 A successful request still emits the performance score, and an eligible serial is retried after the interval
- [x] #3 Targeted regression test and repository gate pass
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a failing per-serial API-error throttle regression test. 2. Record an attempted collection before the API call. 3. Run targeted and repository checks, review, then release.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Regression test failed before the fix (second API call after 3s), then passed after recording the attempt before the SDK call. All 45 MX tests passed; just gen changed no artifacts; just check passed 2976 tests with 91.50% coverage. CodeRabbit review pending rate-limit reset.

CodeRabbit completed with zero findings across the three changed code and instruction files. No metric or label names changed, so the Grafana-query condition was not triggered.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Moved the MX performance per-serial timestamp before the API request, so an unsupported or failed request waits for the solved group interval before retrying. The regression failed before the fix and passed after it; 45 MX tests and just check (2976 tests, 91.50% coverage) passed. just gen produced no artifact diff; CodeRabbit reported zero findings.
<!-- SECTION:FINAL_SUMMARY:END -->
