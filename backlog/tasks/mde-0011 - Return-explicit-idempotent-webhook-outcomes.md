---
id: MDE-0011
title: Return explicit idempotent webhook outcomes
status: To Do
assignee: []
created_date: '2026-08-23 16:42'
labels:
  - 'area:webhooks'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: high
type: bug
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P2.4 and P3.12 remain in core/webhook_handler.py:396-605, models/webhook.py:63, and app.py:1328-1360. Authenticated stale and duplicate deliveries return None and the route maps every None to HTTP 401, while replay keys are committed before downstream state processing succeeds. A processing failure therefore poisons the key and Meraki retries forever. Introduce explicit accepted, duplicate, stale, rejected, and failed outcomes; commit dedupe only after successful processing; require timezone-aware sentAt or normalize it to UTC; and document this as delivery deduplication rather than an anti-replay boundary.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Authenticated duplicate deliveries return 2xx and do not reapply device state
- [ ] #2 A downstream processing failure does not poison the replay cache and a retry can succeed
- [ ] #3 Authentication and schema failures remain non-2xx with bounded failure labels
- [ ] #4 Timezone-naive sentAt values have a deterministic UTC policy covered by tests
- [ ] #5 docs/security.md describes delivery deduplication and its limits
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
