---
id: MDE-0010
title: Bound executor shutdown without blocking the event loop
status: Done
assignee:
  - '@codex'
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 17:40'
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
- [x] #1 SDK executor shutdown cannot block the event loop
- [x] #2 DNS resolver shutdown cannot block the event loop
- [x] #3 Shutdown completes within a configured or frozen bound when worker threads remain blocked
- [x] #4 Tests use blocked fake workers to prove the loop stays responsive and shutdown remains idempotent
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [x] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add failing blocked-worker regressions for the SDK, DNS, and app-owned serving executors, proving a heartbeat coroutine remains responsive, the shared shutdown deadline is respected, and repeated shutdown is idempotent. 2. Add a reusable async executor-drain helper that performs shutdown(wait=True, cancel_futures=True) on a daemon coordinator thread, returns after a frozen five-second deadline, and runs post-drain cleanup only after workers have stopped. 3. Pass one absolute deadline through ExporterApp shutdown so DNS, SDK, and serving pools share the same bound; preserve dependency ordering and log drained versus abandoned fallback outcomes. 4. Correct deployment/scaling documentation, run focused tests, CodeRabbit, make docgen if generated inputs changed, and make check before finalization.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Regression-first evidence: the new SDK/DNS blocked-worker and async-close tests failed against the old synchronous joins (five expected failures). After implementation, 61 focused API client, DNS resolver, app shutdown, harness, async-utils and app-offload tests passed; targeted Ruff and mypy passed. CodeRabbit paid-plan review completed with 0 findings. No generated-doc input or metric/label name changed, so make docgen and Grafana query updates are not applicable.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Bound DNS, SDK and registry-serving executor joins behind one five-second app-level deadline in 361845c. Blocking joins now run on daemon coordinator threads, queued work is cancelled, SDK session cleanup waits for running SDK workers, and deadline expiry defers cleanup to the existing stateless orchestrator force-kill boundary without freezing asyncio. Real blocked-worker regressions prove SDK and DNS close keep heartbeat coroutines responsive, return within the bound and remain idempotent; an app regression proves all three pools share rather than multiply the budget. Verified with 61 focused tests, targeted Ruff and mypy, CodeRabbit paid-plan review (0 findings), and make check (Ruff, format, mypy, 2,747 tests passed). No generated-doc inputs or metric/label names changed, so make docgen and Grafana updates were not applicable.
<!-- SECTION:FINAL_SUMMARY:END -->
