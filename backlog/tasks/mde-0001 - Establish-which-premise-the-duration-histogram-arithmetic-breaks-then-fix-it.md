---
id: MDE-0001
title: 'Establish which premise the duration-histogram arithmetic breaks, then fix it'
status: Parked
assignee: []
created_date: '2026-08-14 15:56'
updated_date: '2026-09-02 15:27'
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
- [x] #5 A regression test pins whatever the correct observation count per run turns out to be
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 1 L8: observe the duration contradiction in the disposable harness, then fix the proven cause alongside explicit group verdict work; root integrates and finalizes.

Wave 1 L3: use the retained fault-injection harness and bounded corpus to establish the duration premise by observation, explain the ClientsCollector residual if possible, and return either verified fixes/tests or a sharper evidence-backed Parked boundary.

Wave 2: root captures and sanitizes the missing live GET corpus, validates a materially closer full ExporterApp replay, then a REVIEW lane observes the duration and ClientsCollector premises; fix only the premise disproven by retained evidence.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-08-23 harness result: one Device wrapper produced exactly one duration observation, one run and one success with about 10.5539 seconds duration, ruling out duplicate observation in that path. The retained harness then failed its post-boundary corpus gate on unrecorded MS packet/STP requests and did not reproduce or explain the historical ClientsCollector residual. No timing fix is justified. Resume with a bounded Clients harness corpus plus the missing MS packet/STP routes, or equivalent retained single-process evidence that reproduces the discrepancy.

2026-09-01 harness observation produced exactly one duration observation for one successful Device wrapper run (10.598551 seconds), but the retained corpus then failed closed on one STP route, two device-specific packet-status routes, and lacks a non-empty Clients route. No production defect was established.

2026-09-02 Wave 2 retained replay: 73 fixtures / 69 operations. Device produced exactly one duration observation for one run and one success (10.583334 s mean inside a 57.410482 s observation window); full-profile startup produced one Device and one Clients observation, so current behavior does not reproduce double counting. The historical Clients 1 Hz excess is explained by the already-fixed disabled child-group loop, but the residual 1.97 Hz cannot be assigned without the deleted process identity/lifecycle provenance. Resume with a native Clients duration observation retaining process identity and injected competing same-collector admission; do not alter production timing without a reproduced false premise.

2026-09-02 main-thread timeline analysis (no new measurement): the historical contradiction is attributable to two defects that were BOTH live during the observation window and BOTH fixed afterwards, which is why three successive harness runs could not reproduce it.

Timeline, read from git and the issue archive:
- Issue #717 was filed 2026-08-12T20:33Z, reporting a container with ~55,200 s (15.3 h) uptime. That container therefore started ~2026-08-12T05:00Z and ran unchanged through the observation.
- 40e24f8 'fix(control): fail closed and serialize forced runs' (#695) landed 2026-08-12T21:36Z — AFTER the observation. It is the commit that made admission atomic: manager.py now acquires the per-collector lock BEFORE awaiting global capacity, with the comment 'Admission must be atomic with the running check ... so a second forced request cannot queue another full run in the check/acquire gap (#695)'. Before it, run_collector_once tested collector_lock.locked() and then awaited the semaphore, leaving exactly the check/acquire gap that lets two runs of the same collector execute concurrently.
- fd5cb69 'fix(clients): schedule only enabled child groups' (#703) landed 2026-08-12T23:51Z — also AFTER the observation. This is the already-credited cause of the ClientsCollector 1 Hz excess.

Consequence for the three premises: premise 2 ('the lock actually serialises') was FALSE in the observed build and is true in current code. That accounts for both the 1.96x oversubscription and, with #703, the ClientsCollector count. No current-code defect is implied, which is consistent with every harness observation to date showing exactly one duration observation per successful run per collector.

This closes the archaeology: process-identity provenance for the deleted container is not needed and must not be pursued further. Remaining work to satisfy AC1-AC4 is bounded and offline: pin the serialisation invariant with a regression that fails against the pre-40e24f8 admission shape, confirm no other observation path can double-count, and settle AC2/AC3 by documenting what the duration metric measures (per-run wall clock excluding lock and admission wait) rather than by changing production timing.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked after bounded harness observation. AC5 is proven; AC1-AC4 remain unproven. Resume with sanitized live-verified captures for the three missing MS routes and a non-empty getNetworkClients response, extend corpus identity to method/path/query, then rerun isolated Device and Clients observations.

Wave 2: parked at a sharper provenance boundary after the expanded retained corpus showed one duration observation per successful Device and Clients wrapper. Current code does not reproduce the historical contradiction; resolving the residual requires process-identity-aware Clients and competing-admission observations, not a speculative timing change.
<!-- SECTION:FINAL_SUMMARY:END -->
