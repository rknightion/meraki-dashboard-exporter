---
id: MDE-0029
title: Bound registry-serving admission instead of queueing scrapes
status: Done
assignee: []
created_date: '2026-08-29 13:05'
updated_date: '2026-08-29 13:20'
labels:
  - 'area:core'
milestone: m-0
dependencies: []
priority: medium
type: bug
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
app.py offloads every full-registry walk (generate_latest for /metrics, _get_metrics_stats for /) onto the two-worker registry-serve pool added for #544/F-026, but nothing bounds admission to it. ThreadPoolExecutor queues without limit, so concurrent scrapers and status-page loads accumulate queued full-registry serializations behind the two workers; each queued caller still holds an event-loop task and each eventually performs a whole redundant registry walk. Under a scrape storm the backlog grows faster than it drains and every caller gets a stale, late response instead of a clear signal. Add explicit admission control in front of the pool: HTTP handlers fail fast when no worker slot is free, the single background cardinality task may wait because its producer is already bounded. Cancellation must not leak a slot - a client that disconnects mid-scrape leaves its worker thread still walking the registry, so the slot has to stay held until the thread finishes, not until the awaiting task unwinds.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 HTTP registry work is admission-controlled so excess callers cannot queue behind the serving pool
- [x] #2 A saturated /metrics scrape is rejected with 503 and Retry-After rather than queued
- [x] #3 A saturated / status-page request is rejected the same way instead of queueing
- [x] #4 The background cardinality walk still waits for a slot rather than failing
- [x] #5 A cancelled request keeps its slot until the running registry walk actually finishes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [x] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a BoundedSemaphore sized to the serving pool's worker count as the admission gate. 2. Route every registry offload through one _run_registry_work helper taking a wait_for_slot flag: HTTP handlers pass False and raise RegistryWorkSaturatedError when no slot is free, the cardinality loop passes True. 3. Release the slot from the executor future's done-callback, not the awaiting task, and await under asyncio.shield so a cancelled request cannot admit new work over a still-running thread. 4. Return 503 with Retry-After from /metrics and / on saturation. 5. Prove both properties with real blocked worker threads: a third concurrent scrape rejected while two workers are occupied, and a cancelled waiter still holding its slot until the thread completes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Chose a BoundedSemaphore admission gate over a bounded work queue: the pool already serialises the expensive part, so the only thing worth bounding is how many callers may be admitted at once, and rejecting is more useful to a scraper than a late answer. Slot release moved to the future's done-callback after reasoning through disconnect: releasing on cancellation would let a new walk start while the cancelled one's thread was still holding a worker, which is the overload the change exists to prevent. Verified with two blocked-thread regressions (a third concurrent scrape rejected 503 while both workers are occupied; a cancelled waiter still holding its slot until the thread completes), 6 app-offload tests, 233 app/metrics/cardinality tests, CodeRabbit paid-plan review on both files (0 findings), and make check (2,787 passed). make docgen re-run and produced no drift; no metric or label name changed, so Grafana queries were not affected.

Follow-up correction (2026-08-29): the review nit claiming a cancelled request leaves asyncio logging 'Future exception was never retrieved' was WRONG. CPython 3.14's asyncio.shield installs _log_on_exception on the inner future when the outer is cancelled (tasks.py:914), which calls loop.call_exception_handler with '<Exc> exception in shielded future' regardless of whether the exception was already retrieved. Retrieving it in the release callback therefore suppresses nothing, and suppression is not wanted anyway: an orphaned registry walk that starts failing must not go quiet because the scraper disconnected first. The attempted fix was reverted; app.py is unchanged from b5bbbbe. Added test_orphaned_registry_walk_failure_is_surfaced_not_swallowed instead, pinning that the failure reaches the loop exception handler exactly once and the slot is still released. Mutation-checked: removing asyncio.shield makes it fail, so it is not vacuous. Note the app sets no custom loop exception handler, so these reports land on the default asyncio logger rather than the app's structlog pipeline.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Bounded admission to the registry-serving pool in b5bbbbe. Every full-registry walk now goes through _run_registry_work behind a BoundedSemaphore sized to the pool: /metrics and / fail fast with 503 and Retry-After when both workers are busy instead of queueing redundant serializations, while the background cardinality walk still waits because its producer is already bounded. The slot is released by the executor future's done-callback under asyncio.shield, so a client disconnecting mid-scrape cannot admit a new walk over its own still-running thread. Verified with blocked-thread regressions proving both the fail-fast rejection and the cancellation-holds-slot property, 233 app-related tests, CodeRabbit (0 findings) and make check (Ruff, format, mypy, 2,787 tests). make docgen produced no drift and no metric or label name changed.
<!-- SECTION:FINAL_SUMMARY:END -->
