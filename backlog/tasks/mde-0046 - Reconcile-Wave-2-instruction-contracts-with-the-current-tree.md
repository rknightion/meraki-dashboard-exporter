---
id: MDE-0046
title: Reconcile Wave 2 instruction contracts with the current tree
status: Done
assignee:
  - '@codex'
created_date: '2026-09-02 08:11'
updated_date: '2026-09-02 08:21'
labels:
  - 'area:docs'
dependencies: []
modified_files:
  - src/meraki_dashboard_exporter/services/CLAUDE.md
  - src/meraki_dashboard_exporter/core/CLAUDE.md
  - src/meraki_dashboard_exporter/api/CLAUDE.md
  - src/meraki_dashboard_exporter/collectors/CLAUDE.md
  - src/meraki_dashboard_exporter/collectors/devices/CLAUDE.md
  - src/meraki_dashboard_exporter/collectors/network_health_collectors/CLAUDE.md
  - src/meraki_dashboard_exporter/collectors/organization_collectors/CLAUDE.md
  - .github/CLAUDE.md
  - tools/apidrift/CLAUDE.md
  - tests/CLAUDE.md
priority: medium
type: docs
ordinal: 46000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The Wave 2 fallback audit found stale concrete claims across ten repository instruction files. Services/core/API contracts overstate inventory exclusivity and omit current sanctioned validation/fallback paths, one metric enum, and the insight controller. Collector contracts undercount current subcollectors and endpoint families. CI/tool/test contracts retain a removed slow-tests job, a retired Claude enrichment step, and a nonexistent test filename. Reconcile only these verified statements against the current tree; AGENTS.md is generated and remains untouched.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Services, core, and API instruction files describe the current inventory enforcement, sanctioned fallback/validation paths, metric enums, and exercised SDK controllers without claiming broader exclusivity than the source provides
- [x] #2 Collector instruction files accurately describe current device, network-health, and organization subcollector composition and response/fallback contracts
- [x] #3 GitHub Actions, apidrift, and test instructions name only current jobs, behavior, and files
- [x] #4 Every corrected path and symbol is rechecked against the tree and the repository documentation gate passes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Apply the exact minimal wording corrections established by the four read-only mapping lanes.
2. Recheck every named path, class, job, endpoint family, and count against current source.
3. Run the proportionate repository gate and finalize the task with objective evidence.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reconciled all ten verified stale instruction files. Services/core/API now distinguish the mandatory filtered network-list path from current bounded device/availability and startup-validation exceptions; collector inventories cover current device, network-health, and organization domains; CI, apidrift, and test references name only current jobs and files. No generator input, metric, label, configuration, endpoint, collector implementation, or Grafana query changed. Validation: git diff --check passed; stale-term scan returned no matches; just check passed with 2913 tests, 5 deselected, and 91.22% coverage; just ci built the image, passed seven structure tests, and received HTTP 200 from /health and /metrics. CodeRabbit was skipped because the change is documentation and tracker text only.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Corrected ten repository instruction contracts against the current source and workflow tree. Verified with exact symbol/path scans, git diff --check, just check (2913 passed, 5 deselected, 91.22% coverage), and the complete Docker-backed just ci gate.
<!-- SECTION:FINAL_SUMMARY:END -->
