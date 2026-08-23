---
id: MDE-0024
title: Complete the 1.1 upgrade and metric-surface notes
status: Done
assignee: []
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:docs'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: medium
type: docs
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #735 documented most configuration compatibility changes from PR #733, but the 1.1 notes still need reconciliation after the surviving fixes. In particular, describe the corrected NetworkFilter series population, the final D6 profile behavior, facade request-attempt semantics, and every deliberately retained startup refusal. docs/changelog.md remains release-please-owned; update hand-written docs or release-please inputs rather than editing generated release output.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every retained 1.1 startup or configuration incompatibility is listed once with operator action
- [x] #2 NetworkFilter users are told that excluded-switch port and power series are removed by the fix
- [x] #3 New or behavior-changed self-observability metrics and their label semantics are documented
- [x] #4 The notes match the final D6, D9, concurrency, and webhook behavior after their dependent tasks land
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
- Reconcile the hand-written 1.1 upgrade notes against the final integrated D6, D9, concurrency, webhook, NetworkFilter, facade, endpoint-verdict, and self-observability behavior.
- Validate documentation and repository gates; do not edit release-please-owned docs/changelog.md.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Completed in 7327153. The 1.1 upgrade notes reconcile startup refusals, NetworkFilter series removal, D6/D9, concurrency, webhook, and self-observability semantics.
<!-- SECTION:FINAL_SUMMARY:END -->
