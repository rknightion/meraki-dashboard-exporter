---
id: MDE-0011
title: Return explicit idempotent webhook outcomes
status: Done
assignee:
  - '@codex'
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 17:53'
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
- [x] #1 Authenticated duplicate deliveries return 2xx and do not reapply device state
- [x] #2 A downstream processing failure does not poison the replay cache and a retry can succeed
- [x] #3 Authentication and schema failures remain non-2xx with bounded failure labels
- [x] #4 Timezone-naive sentAt values have a deterministic UTC policy covered by tests
- [x] #5 docs/security.md describes delivery deduplication and its limits
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [x] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add regression tests for explicit accepted/duplicate/stale/rejected/failed results and route status mapping: authenticated duplicate and stale deliveries return 2xx, authentication/schema rejection stays non-2xx, and internal processing failure returns 5xx. 2. Add a typed WebhookProcessResult with the five frozen outcomes and bounded failure reasons; split replay lookup from commit so the key is stored only after all downstream state processing and success accounting completes. 3. Normalize timezone-naive sentAt to UTC in the Pydantic model and test freshness under a non-UTC process timezone assumption. 4. Document the cache as per-process delivery deduplication, not an anti-replay boundary, including TTL/restart/multi-replica/shared-secret limits. 5. Regenerate endpoint/metric docs if generator inputs change, run focused security and route tests, CodeRabbit, make docgen, and make check before finalization.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Adversarial plan review: keep unauthenticated and schema failure labels on a closed bounded reason set; never return payload-controlled detail; acknowledge stale/duplicate deliveries with 2xx so Meraki stops retrying; return 5xx for retryable processing failure; commit dedupe only after the state applier and success metrics complete; normalize naive sentAt as UTC independent of host timezone; document that the in-memory per-process TTL cache does not stop a secret-holder, survive restarts, or coordinate replicas.

Regression-first implementation now returns a closed accepted/duplicate/stale/rejected/failed result set. Route tests prove 200 duplicate/stale, 401 authentication rejection, 400 schema rejection, and a retryable 500 then 200 then duplicate sequence without a third state application. Naive sentAt normalizes to UTC. Focused webhook/security/route tests passed (51), targeted Ruff/mypy passed, make docgen passed, and CodeRabbit paid-plan review completed with 0 findings.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented explicit accepted, duplicate, stale, rejected and failed webhook outcomes in cbf77b4. Authenticated duplicate/stale deliveries return 2xx without reapplying state; processing failures return 5xx and do not commit deduplication keys, so retry succeeds; authentication/schema failures remain bounded 401/400 outcomes; naive sentAt normalizes to UTC. Security docs now define the per-process TTL cache as delivery deduplication rather than anti-replay protection. Verified with focused webhook tests, make docgen, CodeRabbit paid-plan review (0 findings), and make check (Ruff, format, mypy, 2,752 tests passed). The first full gate found five stale nullable-contract tests, corrected; the next run exposed one unrelated 4-microsecond timing edge that passed in isolation; the final complete run was green. No metric or label names changed, so Grafana updates were not applicable.
<!-- SECTION:FINAL_SUMMARY:END -->
