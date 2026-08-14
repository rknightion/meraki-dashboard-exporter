---
id: MDE-0001
title: 'Establish which premise the duration-histogram arithmetic breaks, then fix it'
status: To Do
assignee: []
created_date: '2026-08-14 15:56'
labels:
  - 'area:observability'
  - 'priority:medium'
  - migrated-from-github
milestone: m-0
dependencies: []
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Migrated from GitHub issue #717 (`question`, `priority: medium`, `area:observability`) on 2026-08-14.
Child of the retired programme tracker #694; closes anomaly **ANOM-1**. Its blocker, the disposable
fault-injection harness (#713), landed on 2026-08-14 in `ed44f79`, so this is unblocked. `7a5f96d`
already added a fail-closed duration-observation test (`Refs #717`) — start by reading it, it is the
existing partial work.

## The contradiction

Three facts read from the tree, which cannot all be true at once:

1. Collector duration is observed **exactly once** per successful `collect()` —
   `src/meraki_dashboard_exporter/core/collector.py:195-201`, labelled by class name.
2. `run_collector_once` **skips** when the per-collector lock is held —
   `src/meraki_dashboard_exporter/collectors/manager.py:711` tests `collector_lock.locked()` and
   returns, so two runs of the same collector should never execute concurrently.
3. `start_time` is set inside `collect()`, *after* the lock is acquired, so duration should exclude
   lock and semaphore wait.

Observed soak values contradict all three together. Over a container uptime of ~55,200 s,
`DeviceCollector` recorded `duration_seconds_count = 1,560` and `duration_seconds_sum = 108,468.71`
— a 69.5 s mean and **108,468 s of execution inside a 55,200 s window**. That is 1.96x
oversubscription, impossible if runs genuinely serialise and duration genuinely excludes waiting.

The original audit filed this as "unexplained provenance" and stopped. It is stronger than that:
**one of the three facts above is false**, and each candidate is its own defect —

- more than one observation per logical run (double counting, or sub-collectors sharing the label);
- the lock does not actually serialise. Note `manager.py:711` checks `locked()` *before* awaiting
  the semaphore, so admission is racy — the same non-atomicity as audit finding F-L8-01;
- duration includes queue or semaphore wait after all.

## Why it needs the harness rather than more source reading

Source reading has already reached a dead end, and the container that produced those counters no
longer exists: a push to `main` rebuilt `:main` and watchtower replaced it before the audit's first
snapshot. Only an isolated, instrumented process settles which premise is false. Use the #713
harness (`ed44f79`) — never a cross-push counter comparison on the live soak host.

Related, possibly the same root cause: `ClientsCollector` recorded **108,790** observations against
`DeviceCollector`'s 1,560. The 1 s wake loop fixed under #703 (`fd5cb69`) accounts for the order of
magnitude, but the audit noted a residual ~2x discrepancy it could not explain.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Which of the three facts is false, established by observation on the #713 harness, not by argument
- [ ] #2 The underlying defect fixed, or recorded as correct-with-a-misleading-metric-name and the metric renamed or re-documented
- [ ] #3 rate(duration_sum)/rate(duration_count) yields a mean an operator can trust for capacity work, or the metric stops implying that it does
- [ ] #4 The residual ClientsCollector ~2x discrepancy is explained, or shown to be the same cause
- [ ] #5 A regression test pins whatever the correct observation count per run turns out to be
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
