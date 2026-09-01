---
id: MDE-0045
title: Reconcile per-directory agent contracts after the overnight changes
status: Done
assignee: []
created_date: '2026-09-01 23:47'
updated_date: '2026-09-01 23:56'
labels:
  - 'area:docs'
dependencies: []
priority: medium
type: docs
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The fallback audit found unambiguous drift across the 17 in-repository CLAUDE.md contracts after the API facade rollout, UI v2 restyle, collector expansion, test-suite growth, and CI security changes. Stale instructions can send later agents down unsupported direct-SDK paths or hide real files and gates.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All 17 CLAUDE.md files are inspected against the current tree and every unambiguous stale claim found by the audit is corrected
- [x] #2 API examples route Meraki SDK calls through the shared facade and identify the pinned Meraki SDK version correctly
- [x] #3 Template, collector, chart, and test inventories match the files and current runtime contracts
- [x] #4 No application behavior or generated artifact changes are introduced
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Audit all 16 instruction files against the live tree; patch only mechanically provable drift in the root, source-package, API/core, collector-domain, chart, and tests contracts; validate referenced paths and run the repository gate.

Live enumeration found 17 instruction files, not the goal document’s stated 16; include the root plus all 16 per-directory files.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The live tree contains 17 CLAUDE.md files: one root contract plus 16 per-directory contracts. The goal’s count of 16 omitted the root file, so the audit used the complete live census.

Validated the complete live census: instruction_files=17, non_instruction_source_changes=0, stale_claim_patterns=0. just check passed with 2,829 tests, 5 deselected, 91.23% coverage; Ruff, formatting, mypy, generated-doc drift, offline API conformance, and the Trivy exception validator all passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Reconciled all 17 CLAUDE.md contracts against the current tree. Corrected stale workflow/chart/UI/API-facade/SDK/collector/test/harness/apidrift guidance without changing application behavior or generated artifacts. Verified by the live file census, diff-scope checks, stale-pattern checks, and just check: 2,829 passed, 5 deselected, 91.23% coverage.
<!-- SECTION:FINAL_SUMMARY:END -->
