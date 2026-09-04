---
id: MDE-0066
title: Repair the MS per-device port-usage fallback after ID-only labels
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
ordinal: 66000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The post-v2 live soak confirmed that the per-device port-usage fallback fails before its API call. `collect_device_port_usage_metrics()` builds an ID-only device-label map and then reads `device_labels["name"]` for LogContext (`src/meraki_dashboard_exporter/collectors/devices/ms.py:1272-1284`), while the label helper deliberately removed display-name keys (`src/meraki_dashboard_exporter/core/label_helpers.py:21-65`). `DeviceCollector` invokes this helper when the organization usage path fails or is unavailable (`src/meraki_dashboard_exporter/collectors/device.py:981-1005`). The concrete result is one swallowed `KeyError("name")` per switch, counted as `unknown`, before `getDeviceSwitchPortsStatuses` runs; the live soak observed four such errors while top-level DeviceCollector failures remained zero. Tests exercise `ms_collector.collect()` but never call this fallback helper directly (`tests/unit/collectors/test_ms_collector.py:1470-1499`). This is a live medium-severity defect: when status bulk collection succeeds but usage bulk collection fails, the intended usage fallback emits nothing, and the top-level success counter masks it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The per-device port-usage fallback takes its logging display name from the device input rather than the ID-only Prometheus label map
- [x] #2 A failing-before focused regression drives the fallback helper directly and proves its API call and representative usage emission complete without a name label
- [x] #3 The DeviceCollector fallback path records no unknown error for this case and retains ID-only metric labels
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-04 main thread. Failing-first evidence: driving collect_device_port_usage_metrics directly raised KeyError: 'name' at ms.py:1279 inside the LogContext construction, before getDeviceSwitchPortsStatuses ran — exactly the reported mechanism. After sourcing the display name from the device input with device.get('name', ''), the same regression showed the API call completing, the response validating with name=sw1 in the log context, and meraki_ms_port_traffic_bytes_per_second emitted with ID-only labels and no name label.

Metric labels are unchanged: create_device_labels still omits the display name per #534, and only the logging context reads it. Focused result: 49 passed for the MS module. Full gate: just check 2945 passed, 5 deselected, 91.49% coverage. CodeRabbit reported 0 findings.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed in 84aa7e8. The per-device port-usage fallback now takes its logging display name from the device input rather than the ID-only Prometheus label map, so it no longer raises KeyError before its API call. Verified by a focused regression driven directly against collect_device_port_usage_metrics, watched failing with KeyError: 'name' at the LogContext line and passing afterwards with the API call made and meraki_ms_port_traffic_bytes_per_second emitted under ID-only labels. MS module 49 passed; just check 2945 passed at 91.49% coverage; CodeRabbit 0 findings. DoD2: the generated-drift gate passed with no declaration change. DoD3: metric labels are unchanged and remain ID-only, so no Grafana query needed updating.
<!-- SECTION:FINAL_SUMMARY:END -->
