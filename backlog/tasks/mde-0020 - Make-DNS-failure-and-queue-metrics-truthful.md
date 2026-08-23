---
id: MDE-0020
title: Make DNS failure and queue metrics truthful
status: Done
assignee: []
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:clients'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: low
type: bug
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P3.6/P3.7 remain in services/dns_resolver.py:285-525 and collectors/clients.py:1545-1620. with_timeout uses the same sentinel for timeout and arbitrary exceptions, so lookup_timeouts counts non-timeout failures. queue_peak_depth reports the bounded handoff queue and saturates at max_concurrent_lookups, hiding the producer backlog and racing across concurrent batches. Separate failure causes and expose a queue/backlog measure whose value changes with real pending work.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Only actual deadline expiry increments the DNS timeout counter
- [x] #2 Resolver exceptions have a separate bounded outcome signal
- [x] #3 Queue or backlog metrics distinguish a small batch from a fleet-sized pending batch
- [x] #4 Concurrent resolve_multiple calls cannot reset or corrupt each others measurements
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 1 L5: separate DNS failure causes and concurrency-safe backlog accounting alongside the privacy audit; root integrates and finalizes.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented and verified in 7327153. DNS timeout/failure and producer backlog signals are exclusive and overlap-safe; full gates passed.
<!-- SECTION:FINAL_SUMMARY:END -->
