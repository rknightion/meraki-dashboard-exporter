---
id: MDE-0007
title: Enforce D9 origin-bound credential stripping
status: In Progress
assignee:
  - '@codex'
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 16:52'
labels:
  - 'area:security'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
documentation:
  - backlog doc doc-0004
priority: high
type: bug
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #735 changed src/meraki_dashboard_exporter/api/client.py:24-65 to preserve Authorization across origin changes when the destination host has a Meraki-owned suffix. That resolves PR #733 P1.2 by contradicting frozen decision D9, which requires credentials to be stripped unconditionally whenever the origin changes. Restore an origin comparison based on the request origin in effect before redirect handling; same-origin explicit default ports remain equivalent, but every changed scheme, host, or port loses Authorization. Do not weaken the operator-selected custom-base-url policy.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Authorization is preserved for same-origin requests including equivalent explicit default ports
- [ ] #2 Authorization is stripped for every cross-origin request, including another Meraki-owned host
- [ ] #3 Lookalike hosts and scheme or port changes are covered by regression tests
- [ ] #4 The implementation and docs agree with frozen decision D9
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Replace Meraki-domain suffix trust with configured-origin equality. 2. Reverse the shard-host regression test and add scheme/port boundary coverage. 3. Run the focused transport tests, then the repository gate and security review before commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Red proof: uv run pytest -q tests/unit/test_697_698_api_transport.py -k "697 or meraki or scheme_or_port" failed 2 tests because shard-host and non-default-port requests retained Authorization. After the implementation change the same selection passed 10 tests. CodeRabbit reviewed the staged security diff on the rknightion plan with 0 findings. Final gate: make check passed ruff, format (377 files), mypy (121 source files), and 2737 pytest tests with 1 Starlette deprecation warning.
<!-- SECTION:NOTES:END -->
