---
id: MDE-0047
title: Make the shipped resource defaults and scaling guidance internally honest
status: To Do
assignee: []
created_date: '2026-09-02 15:56'
updated_date: '2026-09-02 15:57'
labels:
  - 'area:deploy'
  - 'area:docs'
  - 'priority:high'
dependencies: []
type: task
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Split out of MDE-0002 on 2026-09-02. MDE-0002's AC1 and AC3 need a genuine multi-network MEDIUM topology and a genuine dense-MS topology to measure; no reachable organisation has either, so those two criteria are unmeasurable and MDE-0002 stays permanently Parked on them. Everything in MDE-0002 that does NOT depend on a missing topology moves here.

**The binding constraint: no number may be invented.** Where a figure cannot be measured, the fix is to state what it rests on and label it a projection with its inputs, not to replace one unsourced number with another. D11 is untouched — this task must not set a default from a judgement call.

## Mechanism 1 — the shipped default silently contradicts its own documentation

`charts/meraki-dashboard-exporter/values.yaml` renders 256Mi request / 512Mi limit unconditionally. The comment block immediately above it says those values are sized for SMALL only (~1 org / ~10 networks / ~100 devices) and that 'The old "512Mi is enough" advice is WRONG at scale and will OOMKill the pod'. A chart consumer who installs without reading values.yaml comments gets the SMALL default silently at any fleet size. The tiered guidance exists; nothing surfaces it at install time.

## Mechanism 2 — the LARGE series figure is the stale estimate this work was meant to retire

`docs/scaling-guide.md:238` and `charts/meraki-dashboard-exporter/values.yaml:395` both carry 'registry 0.6-1.1M series at LARGE'. That figure predates the per-entity cardinality that IS measured: about 74 live series per observed switch port (`src/meraki_dashboard_exporter/collectors/devices/ms.py`), and 2,225 meraki_ms_* samples over 30 ports. A projection built from measured per-entity cardinality times a stated fleet shape is sourced arithmetic; 0.6-1.1M is not. Replace it with the former, show the inputs, and label it a projection rather than a measurement.

## Mechanism 3 — there is no dense-port-family opt-out

`core/config_models.py` carries `ms_port_usage_interval` (a cadence gate) and `ms_port_status_use_org_endpoint` (an endpoint choice). Neither lets an operator drop the dense per-port series families while keeping the rest of the MS surface. At the measured ~74 series per port, a dense switch fleet is the dominant cardinality contributor and an operator has no switch to pull short of disabling the whole device collector.

## Out of scope

Setting a MEDIUM resource default from measurement, and producing a measured DENSE-SWITCH series figure. Both stay on MDE-0002 and both are blocked on hardware that does not exist. Do not relabel a fixture as MEDIUM to close them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The shipped chart default is unambiguous at install time about the fleet size it covers: an operator who never reads values.yaml comments still learns, at install or at startup, that the default is SMALL-scoped
- [ ] #2 The 0.6-1.1M LARGE series figure is replaced everywhere it appears with a projection derived from the measured per-entity cardinality, with its inputs and fleet-shape assumptions stated inline and labelled a projection rather than a measurement
- [ ] #3 docs/scaling-guide.md and the chart sizing comments agree with each other on every tier, with no figure present in one and absent or different in the other
- [ ] #4 A documented setting exists that disables the dense per-port MS series families while leaving the rest of the MS collector working, with its cardinality effect stated
- [ ] #5 Scrape render time and payload size are reported for the largest fixture the harness can actually populate, checked against a typical Prometheus scrape timeout and the two-thread serving executor, and labelled with the fixture that produced them
- [ ] #6 No resource default is changed on the basis of an unmeasured or invented number; if a default moves, its source measurement is cited inline at the point of change
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Split out of MDE-0002 on 2026-09-02. Inherits its old AC2, AC4 and AC5. MDE-0002 keeps only the two criteria that need topologies no reachable organisation has, and is permanently Parked on them. See MDE-0002's notes for the split record and for why its AC6 calibration gate (cold replay compared against a warm long-running anchor) may be unsatisfiable as written.
<!-- SECTION:NOTES:END -->
