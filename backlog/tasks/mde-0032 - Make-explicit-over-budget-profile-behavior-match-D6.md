---
id: MDE-0032
title: Make explicit over-budget profile behavior match D6
status: Done
assignee: []
created_date: '2026-09-01 21:56'
updated_date: '2026-09-01 22:55'
labels:
  - 'area:scheduler'
  - 'priority:high'
dependencies: []
priority: high
type: bug
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Release review finding P1.5 remains live at src/meraki_dashboard_exporter/collectors/manager.py:638-649. The startup gate rejects only an unset profile, while explicitly selecting standard or full can acknowledge the same over-budget solved plan without changing its demand. Reconcile validation and diagnostics with frozen decision D6: explicit profile selection is required above the computed threshold, priority 1 and 2 retain floors, and lower priorities shed when the selected profile still exceeds budget.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Unset adaptive over-budget plans fail with actionable diagnostics naming measured demand and profile options
- [x] #2 Explicit availability, standard, and full profiles each follow the documented D6 floor and shedding behavior when over budget
- [x] #3 Fixed scheduler mode does not apply adaptive demand validation
- [x] #4 Tests cover unset and all three explicit profiles, and docs describe the selected-profile contract
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Root-owned manager seam: reconcile explicit adaptive profile selection with D6 by proving the selected profile applies its priority floor and shedding policy; retain fixed-mode behavior and update tests/docs.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
D6 behavior was retained and pinned across unset, availability, standard, full, and fixed mode. Explicit profiles solve and apply their floor/shedding contract rather than being treated as a demand-reduction claim. Integrated gate: 2827 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Aligned the explicit-profile contract with D6 through full profile/fixed-mode regression coverage and documentation; just check and just ci pass.
<!-- SECTION:FINAL_SUMMARY:END -->
