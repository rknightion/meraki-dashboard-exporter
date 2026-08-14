---
id: MDE-0004
title: 'MV: migrate off the deprecated camera analytics endpoints'
status: To Do
assignee: []
created_date: '2026-08-14 15:57'
labels:
  - 'area:mv'
  - enhancement
  - 'priority:low'
  - migrated-from-github
dependencies: []
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Migrated from GitHub issue #691 (`enhancement`, `priority: low`, `area:mv`) on 2026-08-14. Standalone,
not part of the hardening programme. Surfaced via the drift tracker #686; apidrift began reporting
these as `INFO op-deprecated` under #690.

## Problem

All five `/devices/{serial}/camera/analytics/*` operations are marked `deprecated: true` in the Meraki
OpenAPI spec (1.72.0 and 1.73.0 — pre-existing, not new drift). The exporter consumes two, in
`src/meraki_dashboard_exporter/collectors/devices/mv.py`:

| consumed op | used for | metric |
| --- | --- | --- |
| `getDeviceCameraAnalyticsZones` | zone config + names | `meraki_mv_analytics_zones`, `meraki_mv_zone_info` |
| `getDeviceCameraAnalyticsRecent` | per-zone person count | `meraki_mv_people_count` |

No removal date is published and the spec carries no `x-sunset` or replacement pointer, only a generic
`x-deprecation-notice`. So this is not urgent, but it is a known future `BREAKING missing-op` and
should be planned rather than discovered.
Deprecated operations: <https://developer.cisco.com/meraki/api-v1/deprecated-operations/>

## Replacement surface

The org-level boundaries + detections API is the successor, and none of it is deprecated:

| deprecated | replacement | params |
| --- | --- | --- |
| `getDeviceCameraAnalyticsZones` | `getOrganizationCameraBoundariesAreasByDevice` | `organizationId` (req), `serials` (opt) |
| | `getOrganizationCameraBoundariesLinesByDevice` | `organizationId` (req), `serials` (opt) |
| `getDeviceCameraAnalyticsRecent` | `getOrganizationCameraDetectionsHistoryByBoundaryByInterval` | `organizationId`, `boundaryIds`, `ranges` (all req); `duration`, `perPage`, `boundaryTypes` (opt) |

Two things make this attractive beyond clearing the deprecation. It is **org-wide bulk, replacing
per-device loops** — today `_collect_analytics_zones` and `_collect_analytics_recent` each fire once
per camera, and boundaries collapse to one or two calls per org, the direction the rate-limit budget
prefers. And boundaries come back already keyed by `networkId` + `serial`, so the existing zone-info
join survives.

## The semantics problem

Detections are **flow, not occupancy**. There is no field that reproduces `averageCount`, so the
migration cannot preserve `meraki_mv_people_count` as-is. Options:

- **A.** Replace the gauge with in/out counters (`meraki_mv_boundary_detections_in_total` / `_out_total`).
  Honest to the new data, but a breaking metric change for any dashboard or alert on
  `meraki_mv_people_count`, and net occupancy has to be derived (cumulative in-out, which drifts).
- **B.** Keep `meraki_mv_people_count` on the deprecated endpoint until Cisco removes it and add the
  boundary counters alongside as the forward path. Costs a period of dual collection.
- **C.** Migrate only the zones/config half now (a genuine like-for-like with a bulk-call win) and
  defer the `recent` -> `detections` decision until a sunset date is announced.

**The issue recommended C.** A later run recorded a preference for **A**, conditional on live evidence
supporting it — the migration must remove occupancy semantics rather than silently reuse their metric
name. **Record the decision explicitly before coding**, and if `ranges`, `counterMode`, the ID
namespaces or the request caps cannot be verified against a capable org, **park this task** rather
than encoding a guessed request shape or a fabricated fixture.

## Live verification needed first (read-only GETs only)

A working key for a personal org is in the gitignored `.env`. Gate on the key being valid and the
selected org owning an MV camera with a configured boundary before probing; do not turn an
exploratory failure into an unbounded probe loop; never make a mutating request.

- `boundaryIds` is **required**, so detections needs a two-phase fetch (boundaries, then detections
  keyed by the IDs returned). `perPage` maxes at 1000, but the cap on `boundaryIds` per request is
  undocumented — confirm it.
- `ranges` is required and its item shape is not described in the spec beyond "a list of time ranges
  with intervals". Confirm against the live API.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The A / B / C decision is recorded on this task before any code is written
- [ ] #2 Boundaries and detections response shapes live-verified against a capable org, read-only, behind a capability gate
- [ ] #3 The ranges item shape and any boundaryIds cap documented in evidence/
- [ ] #4 The zones half migrated: getDeviceCameraAnalyticsZones replaced by the boundaries ops, the per-camera loop removed, meraki_mv_analytics_zones and meraki_mv_zone_info preserved
- [ ] #5 Pydantic models carry __meraki_op__ for whichever new ops land
- [ ] #6 If occupancy semantics change, the metric is renamed rather than silently redefined, and grafana/ queries plus docs/upgrading.md are updated
- [ ] #7 If live verification is not possible, this task is Parked with the exact missing capability named — no guessed request shape, no fabricated fixture
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
