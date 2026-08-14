---
id: MDE-0002
title: Size the Helm resource defaults from a measured MEDIUM-class fleet
status: To Do
assignee: []
created_date: '2026-08-14 15:56'
labels:
  - 'area:deploy'
  - 'area:docs'
  - 'priority:high'
  - migrated-from-github
milestone: m-0
dependencies: []
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Migrated from GitHub issue #712 (`priority: high`, `area: docs`, `area:deploy`) on 2026-08-14.
Child of the retired programme tracker #694; decision **D11**; closes audit findings **F-L7-01** and
**F-L4-01**. Its blocker, the seven-preset fleet fixture generator (#707), landed 2026-08-12
(`fa76729`, `8383656`), so this is unblocked.

**D11 is binding: the new default must come from the MEDIUM-class preset's MEASURED RSS, not a
judgement call.** Otherwise 512Mi is simply replaced by another number with nothing behind it. If no
calibrated measurement can be produced, the correct outcome is to keep the current defaults and
record the missing product decision — not to relabel a fixture as MEDIUM.

Two further constraints inherited from the last run's decisions:

- **Reuse the full exporter runtime.** Component-level allocation figures are not sizing evidence.
  Calibration must exercise the real registry, caches, collection path, `/metrics` render path and
  process RSS. The HOMELAB preset must reconcile materially with the 148.19 MiB / 4,835-series
  anchor before MEDIUM or DENSE-SWITCH numbers may move a default.
- **Do not invent a literal MEDIUM preset.** First establish from `#707`'s work and the durable docs
  whether `BRANCH-RETAIL` is the programme's intended MEDIUM-class shape. If that is not provable,
  retain the defaults and record the gap.

## Mechanism — F-L7-01

`charts/meraki-dashboard-exporter/values.yaml:358-383` always renders 256Mi request / 512Mi limit
regardless of fleet size. The chart's own comments call 512Mi SMALL-only and say it **will OOMKill at
scale**, and `docs/scaling-guide.md:215-233` says LARGE needs 1.5Gi request / 3Gi+ limit. So the
documented contract and the shipped default contradict each other, and a 500-network install
OOMKills with the answer sitting in a comment.

## Mechanism — F-L4-01

About **74 live series per observed switch port** (`src/meraki_dashboard_exporter/collectors/devices/ms.py:85`),
with no default port-family profile, and `generate_latest(REGISTRY)`
(`src/meraki_dashboard_exporter/app.py:992-1008`) serialising the whole registry on one of two
serving threads. Measured: 2,225 `meraki_ms_*` samples over 30 ports; 4,627 samples / 738,423 bytes
rendered in 0.223904 s. Projections — MEDIUM ~215k, LARGE ~2.1m, XL ~9.5m series, with LARGE
wire/time around 335 MB / 102 s if rendering stays linear. The chart and docs claim 0.6-1.1m for
LARGE, from stale evidence. **Both figures rest on assumed fleet mixes**, which is exactly what the
#707 presets replace.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 F-L7-01 — shipped defaults cover a measured MEDIUM fleet, with the source measurement cited in the values.yaml comment
- [ ] #2 LARGE guidance kept in docs/scaling-guide.md and the chart comments, and made consistent with the measurement
- [ ] #3 F-L4-01 — the LARGE series projection is replaced by a measured DENSE-SWITCH figure, and the stale 0.6-1.1m estimate corrected everywhere it appears
- [ ] #4 Scrape render time and payload size measured at DENSE-SWITCH, and checked against a typical Prometheus scrape timeout and the two-thread serving executor
- [ ] #5 If dense port families must be opt-out to stay viable, that switch exists and is documented
- [ ] #6 Calibration reconciles HOMELAB against the 148.19 MiB / 4835-series anchor before any default moves; if it cannot, defaults are unchanged and the missing product decision is recorded here instead
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
