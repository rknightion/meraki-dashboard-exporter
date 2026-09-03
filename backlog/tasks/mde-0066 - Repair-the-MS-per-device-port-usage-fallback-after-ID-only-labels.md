---
id: MDE-0066
title: Repair the MS per-device port-usage fallback after ID-only labels
status: To Do
assignee: []
created_date: '2026-09-03 19:58'
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
- [ ] #1 The per-device port-usage fallback takes its logging display name from the device input rather than the ID-only Prometheus label map
- [ ] #2 A failing-before focused regression drives the fallback helper directly and proves its API call and representative usage emission complete without a name label
- [ ] #3 The DeviceCollector fallback path records no unknown error for this case and retains ID-only metric labels
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
