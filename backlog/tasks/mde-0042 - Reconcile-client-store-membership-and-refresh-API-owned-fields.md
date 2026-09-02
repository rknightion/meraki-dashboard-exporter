---
id: MDE-0042
title: Reconcile client-store membership and refresh API-owned fields
status: Done
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-02 07:54'
labels:
  - 'area:clients'
  - needs-triage
dependencies: []
priority: medium
type: bug
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found successful client snapshots only upsert IDs and never remove departed clients, so stale entries can permanently consume the global cap. Existing records also retain stale display and identity fields such as description, manufacturer, OS, network name, and organization association.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A successful complete snapshot removes departed clients before admitting replacements under the global cap
- [x] #2 Failed or deliberately truncated snapshots do not erase retained data
- [x] #3 Existing client records refresh all API-owned display and identity fields while preserving only intentionally derived state
- [x] #4 Tests cover churn replacement, network rename, and changed description or manufacturer
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 2 L1: freeze complete_snapshot=True only after every selected network fetch succeeds without truncation; add failing churn and field-refresh tests first; reconcile membership before cap admission only for complete snapshots; preserve derived DNS state; run focused checks and return evidence without tracker or external writes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 3 reproduced stale client membership and stale API-owned fields. Correct reconciliation depends on distinguishing complete snapshots from emission-capped or failed fetches.

Wave 2 red: complete/incomplete snapshot regressions failed with TypeError because ClientStore.update_clients had no complete_snapshot signal. The collector now asserts completeness only when every selected network fetch succeeds without truncation; complete snapshots reconcile membership before cap admission, incomplete snapshots retain data, and API-owned fields refresh while derived DNS state survives. Green: 4 focused tests, typecheck, and just check with 2913 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked after audit. Resume by freezing a complete-snapshot signal at the collector/store seam, then reclaim departed IDs before cap admission and refresh every API-owned field without erasing derived state.

Wave 2: added an explicit complete-snapshot seam, reclaimed departed clients before cap admission only for complete fetches, and refreshed API-owned identity/display fields without erasing derived state. Verified by churn, truncation, rename, and field-refresh regressions plus just check.
<!-- SECTION:FINAL_SUMMARY:END -->
