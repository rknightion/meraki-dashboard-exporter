---
id: MDE-0065
title: Omit absent network filters from organization MS port requests
status: Done
assignee: []
created_date: '2026-09-03 19:58'
updated_date: '2026-09-03 23:07'
labels:
  - 'area:ms'
  - needs-triage
dependencies: []
priority: medium
type: bug
ordinal: 65000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The post-v2 live soak confirmed a default-path API accounting and fallback defect. `OrganizationInventory.get_allowed_network_ids()` returns `None` when filtering is inactive (`src/meraki_dashboard_exporter/services/inventory.py:187-218`), but both organization-wide MS port paths always pass that value as `networkIds` (`src/meraki_dashboard_exporter/collectors/devices/ms.py:926-939` and `1491-1505`). The installed SDK serializes the keyword and the live API rejects it as an invalid network ID, so each due cycle spends failed calls and falls back to per-device collection even though no filter was requested. During an observed healthy soak, the manager still reported successful DeviceCollector cycles while its `api_client_error` series rose from 1 to 6. `tests/unit/collectors/test_ms_collector.py:41` configures the inactive-filter result but its mocks accept arbitrary keywords and no test asserts that the absent filter is omitted. This is a live medium-severity defect: collection recovers, but the preferred bulk path is unusable, API budget is wasted, and health hides the repeated endpoint failure.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 With no active NetworkFilter, neither organization-wide MS port endpoint receives a networkIds keyword and both calls can complete without the current invalid-filter response
- [x] #2 With an active non-empty filter, the resolved network IDs are still passed; an active filter resolving to zero networks still makes no API call
- [x] #3 Focused regressions cover status and usage paths for absent, non-empty and empty filters and reconcile API-call and fallback behavior
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-04 main thread. Failing-first evidence: the two omit-keyword regressions failed with networkIds present and set to None, while the non-empty-filter and empty-filter regressions passed unchanged, confirming the defect is specific to the inactive-filter case.

The audit found a THIRD call site the task description did not name: getOrganizationSwitchPortsClientsOverviewByDevice inside collect_port_usage_by_switch shared the same network_ids variable and therefore the same defect. All three now build a filter_kwargs mapping that is empty when get_allowed_network_ids returns None and carries sorted IDs otherwise, so the keyword is omitted rather than serialized as null. The zero-match short circuit is untouched.

Focused result after the fix: 49 passed for the whole MS collector module, including the two collateral usage-path tests that broke mid-change. Full gate: just check 2945 passed, 5 deselected, 91.49% coverage. CodeRabbit reported 0 findings across both changed files.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed in 84aa7e8. All three organization-wide MS port call sites (statuses-by-switch, usage-history-by-device, and the previously unnamed clients-overview-by-device) now omit networkIds entirely when no filter is configured, instead of serializing an explicit null the API rejects. Non-empty filters are still passed sorted and a zero-resolving filter still short circuits. Verified by five focused regressions, two of which were watched failing with the keyword present and None; MS module 49 passed; just check 2945 passed at 91.49% coverage; CodeRabbit 0 findings. DoD2: just check's generated-drift gate passed with no metric, config, endpoint or schema change. DoD3: no metric or label name moved, so no Grafana query needed updating.
<!-- SECTION:FINAL_SUMMARY:END -->
