---
id: MDE-0002
title: Size the Helm resource defaults from a measured MEDIUM-class fleet
status: Parked
assignee: []
created_date: '2026-08-14 15:56'
updated_date: '2026-09-02 15:57'
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
- [ ] #2 F-L4-01 — the LARGE series projection is replaced by a measured DENSE-SWITCH figure, and the stale 0.6-1.1m estimate corrected everywhere it appears
- [x] #3 Calibration reconciles HOMELAB against the 148.19 MiB / 4835-series anchor before any default moves; if it cannot, defaults are unchanged and the missing product decision is recorded here instead
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Replacement lane L11: use the full exporter runtime measurement path with generated HOMELAB, BRANCH-RETAIL, and DENSE-SWITCH fixtures; first prove whether BRANCH-RETAIL is the D11 MEDIUM shape and reconcile HOMELAB to its live anchor. Change resource defaults/docs only if calibrated evidence satisfies the task; otherwise return the contractual unchanged-default Parked boundary.

Wave 1 L4: freeze and justify a literal MEDIUM topology under the 2026-09-01 authority, exercise the full ExporterApp runtime, reconcile HOMELAB first, and update measured sizing guidance only when the calibration contract holds.

Wave 2: consume the same complete live-verified HOMELAB corpus, require calibration materially closer to the 148.19 MiB and 4,835-series anchor, then measure a measurement-defined MEDIUM and DENSE-SWITCH only if that prerequisite holds; otherwise keep defaults and park on named missing routes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-08-23 calibration stop: D2 has no frozen literal MEDIUM preset and the durable archive explicitly says BRANCH-RETAIL is not MEDIUM. The retained four-route corpus cannot populate the full collector, registry, and cache path; HOMELAB produces 4,627 samples rather than reconciling to the 4,835-series / 148.19 MiB live anchor; DENSE-SWITCH lacks live MS port routes and has 96,000 ports, making guessed materialization unsafe. Defaults remain unchanged. Resume after a product decision freezes a literal MEDIUM topology and provenance-bearing complete HOMELAB MR/MS/MT plus DENSE-SWITCH MS response corpora exist, then run a fresh-process full ExporterApp benchmark with a shared no-delay limiter, external RSS, and actual HTTP /metrics payload and render timing.

2026-09-01 measurement: froze MEDIUM as the existing BRANCH-RETAIL preset, one organisation with 750 networks, 4,500 devices, 18,000 switch ports, 3,000 SSIDs and 7,500 clients. It is the only D2 many-network representative and avoids inventing an eighth preset. A full ExporterApp replay of the retained HOMELAB corpus returned HTTP 200, 103.04 MiB RSS, 164 scrape samples, 49,330 bytes and 0.077433 seconds. That is 30.47% below the 148.19 MiB anchor and 96.61% below the 4,835-series anchor, so calibration failed and defaults remain unchanged. Resume after adding provenance-bearing full-profile HOMELAB routes and MS port-status plus other enabled-route corpus needed for BRANCH-RETAIL and DENSE-SWITCH.

The 2026-09-01 operator run contract explicitly authorised root to freeze a literal MEDIUM topology and review it the next morning. That authority supersedes the 2026-08-23 archive position for this measurement only; BRANCH-RETAIL was selected because it is the existing many-network preset, and the failed HOMELAB calibration kept every default unchanged.

2026-09-02 Wave 2 full-runtime HOMELAB replay: HTTP 200, 112803840-byte RSS, 3688 total samples, 2253 product samples, 513757-byte payload, 0.075662 s render. This is materially closer than the prior 103.04 MiB / 164-sample replay but remains 27.41% below the 148.19 MiB RSS anchor and 23.72% below the 4835-sample anchor. MEDIUM remains undefined and DENSE-SWITCH lacks a genuine dense topology; defaults and guidance therefore remain unchanged. Resume with live-verified full-profile captures from an explicitly frozen multi-network MEDIUM topology and an actual dense MS topology, including data-bearing device and switch-port status/packet routes, then rerun this fresh-process HTTP/RSS benchmark.

2026-09-02 main-thread scope review (no new measurement): three successive runs have failed AC6's calibration gate, and the reason is structural rather than a measurement error.

The gate requires a cold, fresh-process replay to reconcile with the 148.19 MiB / 4,835-series anchor, but that anchor was read from a long-running live process which had accumulated inventory cache, client store, DNS cache and metric label sets over hours. A cold single-cycle replay is expected to sit below it. The Wave 2 result (112.80 MiB RSS, 3,688 samples, 27.41% and 23.72% below) is the closest yet and may already represent the ceiling of what a cold replay can reach, so tightening the corpus further may never satisfy AC6 as written.

Independently, AC1 and AC3 require a genuine multi-network MEDIUM topology and a genuine dense-MS topology. The only available live organisation has 1 MR, 2 MS and 16 MT, so neither exists and neither can be acquired. Those two criteria are unmeasurable, not merely unmeasured.

AC2, AC4 and AC5 do not depend on either missing topology and remain achievable: the chart ships a 256Mi/512Mi default while its own comment says 512Mi is SMALL-only and will OOMKill at scale, and the scaling guide's LARGE figures rest on the same stale 0.6-1.1m estimate the task set out to replace. That shipped self-contradiction can be resolved honestly without inventing a MEDIUM number.

2026-09-02 split, operator-approved. Three acceptance criteria moved to MDE-0047 because they do not depend on either missing topology: the old AC2 (LARGE guidance kept consistent between the scaling guide and the chart comments), old AC4 (scrape render time and payload size, reworded there to the largest fixture the harness can actually populate), and old AC5 (a dense-port-family opt-out switch). MDE-0047 carries them.

What remains here is exactly the unmeasurable part: a MEDIUM-fleet resource default (AC1) and a measured DENSE-SWITCH series figure (AC2, renumbered). Both require topologies no reachable organisation has and none can be acquired, so this task is PERMANENTLY Parked and is exempt from the v2 ship gate on the same structural grounds as MDE-0004. It is not exempt from being fixed if the hardware situation ever changes.

Resume condition, unchanged in substance but now the only thing left: a genuine multi-network MEDIUM topology and a genuine dense-MS topology become measurable, at which point rerun the retained fresh-process full-ExporterApp HTTP/RSS benchmark against them. Do not close this by relabelling a synthetic preset.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked after freezing the literal MEDIUM topology and landing a repeatable full-runtime measurement path. The retained corpus materially failed HOMELAB calibration, so no resource default, scaling guidance or dense-family opt-out decision can be justified. Resume with provenance-bearing full-profile HOMELAB and dense MS route captures, then measure BRANCH-RETAIL and DENSE-SWITCH through the same harness.

Wave 2: parked at a sharper topology-and-route boundary. The complete HOMELAB corpus materially improved reconciliation but still leaves about one quarter of RSS and samples unexplained, so D11 cannot justify MEDIUM defaults or DENSE-SWITCH guidance without genuine measured topologies.
<!-- SECTION:FINAL_SUMMARY:END -->
