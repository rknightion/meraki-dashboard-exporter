---
id: MDE-0010
title: Bound executor shutdown without blocking the event loop
status: To Do
assignee: []
created_date: '2026-08-23 16:42'
labels:
  - 'area:core'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: high
type: bug
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P2.3 remains at api/client.py:344-363, services/dns_resolver.py:85-90, and app.py:287-335. Synchronous ThreadPoolExecutor.shutdown(wait=True) joins run on the event-loop thread, so a blocked SDK page or reverse-DNS lookup can freeze probes and exceed Kubernetes termination grace. Move or avoid the joins, apply a bounded shutdown deadline, preserve idempotence, and define the safe fallback when running threads cannot be interrupted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 SDK executor shutdown cannot block the event loop
- [ ] #2 DNS resolver shutdown cannot block the event loop
- [ ] #3 Shutdown completes within a configured or frozen bound when worker threads remain blocked
- [ ] #4 Tests use blocked fake workers to prove the loop stays responsive and shutdown remains idempotent
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
