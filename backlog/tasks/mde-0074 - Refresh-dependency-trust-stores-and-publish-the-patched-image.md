---
id: MDE-0074
title: Refresh dependency trust stores and publish the patched image
status: In Progress
assignee: []
created_date: '2026-10-21T15:28:00Z'
updated_date: '2026-10-21T15:59:00Z'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Full Python 3.14 just ci passed with 2,987 tests and 91.51% coverage; CodeRabbit completed with zero findings across both annotation changes and lockfile. Local Trivy reproduced two HIGH urllib3 findings in pip 26.2.2 vendoring despite its fixed certifi. Removed unused base pip from final runtime rather than weakening exceptions, then reran the full image and source gate successfully.

Merged security fix PR 796 at 6b4e847 and upload-artifact PR 809 at 1a488d8, both on current branches with green exact-head required checks. PR 809 retained its exact pin assertion, updated to the new official action SHA after the old expectation failed. Ubuntu 26 runner PR 795 exposed old actionlint runner-label metadata; all shared refs updated together to published v1.25.11, which recognizes the officially supported label. Full gate passed after that pin fix.
<!-- SECTION:NOTES:END -->
