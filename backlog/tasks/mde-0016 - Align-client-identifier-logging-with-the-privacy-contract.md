---
id: MDE-0016
title: Align client identifier logging with the privacy contract
status: To Do
assignee: []
created_date: '2026-08-23 16:42'
labels:
  - 'area:privacy'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: medium
type: bug
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #735 demoted one DNS change log and removed an IP from with_timeout, but PR #733 P2.14 remains partially reachable: DNSResolver.resolve_hostname still gives AsyncRetry an operation string containing the IP, and client collection DEBUG logs include client IDs and MACs not fully enumerated by docs/privacy.md. Audit INFO/WARNING/ERROR paths for client IP, ID, MAC, hostname, and descriptions; make non-debug operations non-identifying; and state the intentional DEBUG surface precisely.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 INFO, WARNING, and ERROR logs never contain client IP, ID, MAC, hostname, or description values
- [ ] #2 Timeout and retry messages use stable non-identifying operation names
- [ ] #3 Any identifier values intentionally retained at DEBUG are listed in docs/privacy.md
- [ ] #4 Tests capture representative logger events rather than checking source strings only
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
