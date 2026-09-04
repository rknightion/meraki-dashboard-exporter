---
id: MDE-0037
title: Strengthen the static gate against direct SDK call bypasses
status: Done
assignee: []
created_date: '2026-09-01 22:45'
updated_date: '2026-09-02 07:54'
labels:
  - 'area:tests'
  - 'area:api'
  - needs-triage
dependencies: []
priority: high
type: bug
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 3 found that the current AST gate detects only a restricted asyncio.to_thread direct-call form. Direct SDK references in other production roots, run_in_executor, or local aliases can bypass the shared facade without failing the gate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The static gate inspects every production self.api controller method reference in the intended source scope
- [x] #2 Only calls routed through facade_for(...).call(...) or explicit documented exemptions pass
- [x] #3 Tests prove run_in_executor and local-alias bypasses fail
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 2 L4 phase 1: inventory every production self.api controller-method reference, freeze the documented exemption list, add failing run_in_executor and alias bypass fixtures first, then strengthen the AST gate and run focused checks.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 3 reproduced the coverage gap. This is parked because a whole-production AST policy and its exemption list are a high-blast enforcement change outside the fresh-audit low-blast fix rule.

Wave 2 red: the new run_in_executor and local-method-alias fixtures failed before the gate helpers existed; the first complete inventory then exposed ten stored-facade references, all classified into the three frozen documented exemptions. Integration review added a self.api root-alias regression after CodeRabbit found that remaining shape. Green: focused facade gates passed and just check completed with 2913 passed, 5 deselected, 91.22% coverage.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked after audit. Resume by inventorying every production SDK reference, freezing the explicit exemptions, then extend the AST gate with negative fixtures for aliases and run_in_executor.

Wave 2: strengthened the production AST gate to inventory direct SDK method references, admit only facade calls or three documented exemptions, and reject executor, method-alias, and self.api root-alias bypasses. Verified by focused regressions and just check.
<!-- SECTION:FINAL_SUMMARY:END -->
