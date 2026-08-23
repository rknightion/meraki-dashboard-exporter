---
id: MDE-0013
title: Preserve organization-keyed pacing at every facade owner
status: Done
assignee: []
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:api'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: high
type: bug
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #735 made facade_for walk owner and parent links, but PR #733 P2.1/P2.11 are not fully closed. Unresolvable limiters remain silently accepted, MS DHCP-security/link-aggregation fan-outs still depend on transient LogContext state, and _resolve_org_id in core/api_facade.py:158-172 guesses that any 18-character first argument is an organization ID. Make pacing ownership explicit and loud, carry org_id through the affected fan-outs, and remove identifier-shape guessing that can key a network as an organization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every production facade owner resolves a non-None rate limiter or fails loudly before an unpaced call
- [x] #2 MS DHCP-security and link-aggregation calls acquire the configured organization bucket
- [x] #3 Network IDs cannot be inferred as organization IDs from string length
- [x] #4 A tree-level regression check covers facade routing without relying on one fragile AST spelling
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 1 L2: jointly resolve explicit organization pacing with MDE-0014 across the API facade seam; child owns local edits and focused validation, root owns integration and final gate.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented and verified in 7327153. Facade pacing fails closed and preserves explicit organization scope; full gates passed.
<!-- SECTION:FINAL_SUMMARY:END -->
