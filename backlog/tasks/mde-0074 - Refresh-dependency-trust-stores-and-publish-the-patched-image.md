---
id: MDE-0074
title: Refresh dependency trust stores and publish the patched image
status: In Progress
assignee: []
created_date: '2026-10-21T15:28:00Z'
updated_date: '2026-10-21T15:28:00Z'
labels:
  - 'area:dependencies'
  - 'priority:high'
dependencies: []
ordinal: 74000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The published-container Trivy gate on the current main commit reports compromised emSign roots in both application certifi and base-image pip vendoring. The lock-maintenance PR also exposes newer Ruff context-manager typing requirements. Complete the open dependency updates and verify the shipped trust stores without weakening publication gates.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Application and pip vendored certifi are at least 2026.10.19 and Alpine CA packages are patched
- [ ] #2 Open dependency PRs are refreshed and merged only with green exact-head required checks or have a concrete blocker
- [ ] #3 Release publication and both incident-host certificate rejection checks have recorded evidence or a precise unobserved boundary
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Repair newer Ruff context-manager type annotations on the lock-maintenance branch; upgrade base pip to 26.2.2 so its vendored trust store is patched. 2. Run the complete check and image-gate recipes and review the code delta. 3. Refresh and green-merge each dependency PR, then the release PR; read back released trust-store versions and incident-host rejections.
<!-- SECTION:PLAN:END -->
