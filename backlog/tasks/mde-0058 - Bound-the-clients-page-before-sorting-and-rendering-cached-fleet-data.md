---
id: MDE-0058
title: Bound the clients page before sorting and rendering cached fleet data
status: Done
assignee: []
created_date: '2026-09-03 14:43'
updated_date: '2026-09-03 19:30'
labels:
  - 'area:http'
dependencies: []
priority: high
type: bug
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 2 confirmed a major live event-loop defect at the v2.0.0 release tree. src/meraki_dashboard_exporter/app.py:1225-1237 copies, sorts and groups every cached client synchronously, then app.py:1257 and templates/clients.html:9 synchronously render one 19-column row per client. ClientSettings supports 25,000 cached clients by default and up to 1,000,000 at core/config_models.py:1050-1059. A supported large GET /clients can therefore monopolize the event-loop thread while health, metrics, scheduler and disconnect handling wait. Endpoint tests at tests/unit/test_app_endpoints.py:603-632 cover only disabled and missing-collector cases. The narrow reversible remedy is additive server-side pagination with bounded page and page-size parameters; record the chosen default and maximum as an operator decision.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 GET /clients sorts, groups and renders no more than a fixed maximum number of cached clients per request
- [x] #2 Navigation exposes the current page, total pages and bounded next and previous links without disclosing new data
- [x] #3 Focused tests cover a store larger than one page, invalid or excessive query values, and preserve disabled and missing-collector behavior
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add failing store and endpoint regressions for a cache larger than one page, invalid query bounds and responsive concurrent health. 2. Add a bounded ClientStore page snapshot that copies at most the requested page and invoke it off the event loop; use page=1, page_size=250 by default and cap page_size at 1000. 3. Render current/total page metadata with bounded previous and next links, preserving existing disabled and missing-collector behavior. 4. Run focused tests, lint and typecheck, then return the uncommitted diff to root.

5. Resolve review findings by giving client-page work a dedicated single-worker executor with fail-fast admission, publishing per-network client maps copy-on-write, and capturing stable map references under a short store lock before traversal.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Test-first evidence: pagination regressions failed before implementation; the deterministic concurrency regression then failed against overlapping mutable dictionary traversal, and the responsiveness form failed while the first lock design held the lock for the full O(n) walk. The final design publishes per-network maps copy-on-write, captures stable references under a short RLock, traverses on a dedicated bounded client-page executor, and returns 503 with Retry-After when its one slot is occupied. Focused concurrency, endpoint and shutdown tests passed. Integrated just check passed 2,939 tests with 5 deselected at 91.25% coverage, and just ci passed all Docker legs. The default page is 250 and the hard maximum is 1,000; no metric or label name changed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented in 92c3ae7: /clients now renders a bounded navigable page, performs stable cache traversal off the event loop in its own fail-fast worker, does not compete with SDK or registry pools, and shuts the pool down within the shared bound. Copy-on-write publication prevents dictionary races without delaying collection updates.
<!-- SECTION:FINAL_SUMMARY:END -->
