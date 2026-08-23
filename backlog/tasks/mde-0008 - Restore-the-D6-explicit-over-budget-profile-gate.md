---
id: MDE-0008
title: Restore the D6 explicit over-budget profile gate
status: Done
assignee:
  - '@codex'
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 17:18'
labels:
  - 'area:scheduler'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
documentation:
  - backlog doc doc-0004
priority: high
type: bug
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #735 replaced EndpointScheduler.requires_explicit_profile in core/scheduler.py:429 with an unconditional False and made CollectorManager.validate_profile_selection in collectors/manager.py:612 a no-op. That avoids PR #733 P1.5/P2.5-P2.7 crash loops but violates frozen decision D6. Implement the decision coherently: only adaptive mode gates; the threshold is computed from the solved plan versus budget; an implicit over-budget plan refuses startup; an explicit profile is evaluated honestly; and the error names demand, budget, and viable choices. Preserve the full collection surface for an unset profile below the threshold and keep priority 1/2 floors protected.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Adaptive mode refuses an implicit profile only when the computed plan crosses the D6 threshold
- [x] #2 Fixed mode never applies the adaptive explicit-profile gate
- [x] #3 Setting a profile is not a no-op remedy: the selected profile is solved and any invalid choice receives an actionable result
- [x] #4 The pre-yield validation is bounded and cannot create an unbounded inventory warm or a healthy-looking dead background task
- [x] #5 docs/upgrading.md and scheduler diagnostics describe the implemented D6 behavior
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add failing scheduler and manager tests for adaptive-only implicit gating, fixed-mode exemption, explicit-profile solving, actionable errors, and bounded preflight behavior. 2. Restore D6 in EndpointScheduler and CollectorManager without weakening transient-startup tolerance or priority 1/2 floors. 3. Update upgrading and scheduler documentation, run targeted tests and doc generation, then CodeRabbit and make check before finalizing.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented in 3ac6c67cb815e527d0ae4af6b558be6e3d792e02. Restored frozen D6 using the solved implicit full plan versus the adaptive effective-budget target; fixed mode bypasses the gate, affordable unset profiles retain the full endpoint surface, and every explicit profile is solved before startup. The pre-yield inventory warm and solve share one collector_timeout wall-clock bound, with transient failures deferred to normal collection. Priority 1/2 floors remain protected and the refusal names measured demand, budget target, and all profile choices. Updated upgrading, scheduler, scaling, generated config, env, and Helm descriptions. Verification: red tests first (5 intended failures), focused profile suite 13 passed, broader scheduler/startup suite 250 passed, make docgen passed, Helm lint/render passed, and make check passed (ruff, format, mypy 121 files, 2742 tests, one existing Starlette deprecation warning). CodeRabbit major finding about measuring standard instead of the implicit full plan was fixed; its remaining minor generated-Markdown finding is pre-existing and tracked as MDE-0025. Grafana verification was not applicable because no metric or label name changed.
<!-- SECTION:FINAL_SUMMARY:END -->
