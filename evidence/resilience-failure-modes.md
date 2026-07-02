# RES lane report — resilience & failure-mode analysis

Produced 2026-07-02 by the v1-readiness assessment (Fable lane). Method: full read of
app.py, collectors/manager.py, core/{collector,error_handling,metric_expiration,
async_utils,org_health,rate_limiter,webhook_handler,batch_processing,config_models,
cardinality}.py, api/client.py, services/*, all coordinators, Helm probes, Dockerfile —
PLUS two LIVE RUNS of the exporter with an invalid API key and introspection of the
installed Meraki SDK's RestSession.request retry loop. Backs issues #509–#511, #528,
#544–#547, #591, #596, #597, #543.

## RES-01 → #509 (P0) — Total API failure reported as success (LIVE-CONFIRMED)

Mechanism: almost every collector swallows failures before the manager sees them:
`device.py:364-365`, `organization.py:308-309`, network_health.py and config.py (same
pattern), `devices/mt.py:169-170` wrap `_collect_impl` bodies in
`try/except Exception: logger.exception(...)`; org-list fetches are decorated
`@with_error_handling(continue_on_error=True)` (`device.py:367-371`) so a 401 / DNS
failure / unreachable API returns None → "No organizations found" → NORMAL RETURN.
`MetricCollector.collect()` (`core/collector.py:146-191`) then records success;
`_run_collector_with_timeout` (`manager.py:677-748`) increments total_successes, resets
failure_streak, updates last_success_time. Poisoned signals: (a) /ready gate
(`manager.py:586-605`, the F-105 fix) checks total_successes>0 — satisfied by spurious
successes; (b) /health dead-man switch (`app.py:142-177`, F-043) keys off
last_success_time — never trips; (c) collector_success_timestamp_seconds keeps advancing;
(d) failure_streak stays 0; /status shows 100%.

Live-run evidence (fake 40-char key): log shows `getOrganizations - 401 Unauthorized` at
17:24:16, then `Tier initial collection complete tier=fast` 10s later. /status?format=json
at t+60s: MTSensorCollector total_successes=1, success_rate=100.0, staleness=ok. At
t+215s: **/ready → HTTP 200 {"ready":true,...} and /health → HTTP 200**. A pod with a
revoked key passes both Helm probes forever, serves zero meraki_* metrics, never restarts.
The two collectors whose exceptions DO propagate (MTSensorAlertsCollector,
ClientsCollector) can't hold readiness back because tier_had_success = any(...).

Fix directions (in #509): make "collected nothing" count as failure — coordinators
re-raise/return-failure when the org fetch fails or ALL per-org tasks fail (extend the
F-040/F-172 accounting in `organization.py:380-409` to every coordinator); or manager
treats "0 metric updates + ≥1 error increment" as failure; minimum: gate readiness on
`api_requests_total{status_code="200"} > 0`. Regression test: fake-key run must yield
/ready 503 and failure_streak > 0.

## Other findings (filed; full text in findings-synthesis.md)

- RES-02 → #510: `ManagedTaskGroup.__aexit__` gathers with return_exceptions=True and
  only LOGS `_task_exceptions` (`async_utils.py:146-206`); nothing re-raised, no failure
  count exposed — coordinators can't distinguish all-failed from all-OK. Structural root
  of half of RES-01.
- RES-03 → #546: `asyncio.timeout(240)` cancels the coroutine, not the SDK worker
  threads (99 to_thread call sites); torn partial metric state persists up to 2× tier
  interval, then series EXPIRE (vanish) rather than being marked stale.
- RES-04 → #544: all SDK calls + `/metrics` `generate_latest` (app.py:690) + cardinality
  analysis share the DEFAULT executor (min(32, cpu+4) threads); `AsyncMerakiClient._semaphore`
  (api/client.py:52) is created and NEVER USED; during 429 storms scrapes queue behind
  blocked SDK threads. DNS already got a dedicated pool for exactly this reason (F-075).
- RES-05 → #545: retry multiplication — SDK (up to 3 HTTP attempts, sleeping
  int(Retry-After) UNBOUNDED in the worker thread, nginx_429_retry_wait_time=5 when
  header absent) × `with_error_handling` rate-limit retries (3 more, 10–60s backoff, each
  re-entering the SDK's full cycle) ≈ 12 HTTP attempts per logical fetch. Pick ONE 429
  owner. (SDK behavior verified from installed package source.)
- RES-06 → #547: OrgHealthTracker written ONLY by OrganizationCollector
  (`organization.py:394-408`); six collectors read `should_collect()` (`manager.py:44-51`)
  → backoff blind to device/network failure domains; dies entirely if the organization
  collector is disabled via disable_collectors.
- RES-07 → #543: ClientStore never evicts departed clients (`cleanup_stale_networks()`
  and `clear()` have ZERO production call sites; max_clients_per_network caps only
  per-batch inserts). DNSResolver `_cache` (evicted only on read-after-expiry) and
  `_client_tracking` (never pruned) grow unboundedly.
- RES-08 → #596: liveness auto-threshold 3×SLOW = 45 min ≫ metric TTL 2×interval — a
  wedged exporter serves EMPTY metrics ~35–43 min before /health flips.
- RES-09 → #528: the tier-loop "10 consecutive failures → exit" counter (app.py:449-466)
  is dead code (collect_tier effectively never raises); if it DID fire it sets
  _shutdown_event, silently stopping ALL tiers while uvicorn keeps serving.
- RES-10 → #591 (LIVE-CONFIRMED): smoothing offsets apply to the INITIAL collection —
  /ready still 503 at t+63s with MEDIUM collectors at total_runs=0; medium initial
  completion at ~3m30s, slow ~4m20s. Every rolling restart keeps the pod out of
  Endpoints ~3–4 min.
- RES-11 → #597: SIGTERM drain best-effort (0.5s courtesy → cancel → 3s gather →
  close); blocked SDK threads under retry storms can exceed the default 30s grace →
  SIGKILL noise. Stateless, so consequences benign.
- RES-12 → #511: bare-swallow paths increment NO error counter; the one signal surviving
  everything is `api_requests_total{status_code!="200"}` — but only for inventory-routed
  calls.

Clusters: {RES-01,02,12} failure masking — fix together. {RES-03,04,05} thread-pool +
retry design — one design pass (dedicated SDK executor + single retry owner).

## Checked and found OK (do not re-flag)

- Startup with unreachable API / DNS failure / discovery failure: process does NOT crash;
  uvicorn binds immediately (F-104); /metrics during startup returns 200 with process +
  exporter-internal metrics; /health correctly 200 ("starting") pre-collection; /ready
  correctly 503 early (verified live at t+8s). The failure is what happens AFTER (#509).
- Config errors at startup: missing/short key → clean actionable error, exit 1; network
  filter resolving to zero networks across ALL orgs → hard RuntimeError with per-org
  ERROR logs (`manager.py:481-514`).
- asyncio.timeout + per-collector lock: lock released on cancellation; overlapping runs
  of the same collector skipped with a warning; utilization gauge + >0.8 warning exists.
- Readiness design: gate excludes SLOW deliberately; Helm probes correctly split /health
  (liveness) vs /ready (readiness); Dockerfile HEALTHCHECK present.
- Metric expiration manager removes real registry series (Gauge.remove); bookkeeping
  bounded by the cap; cleanup task properly lifecycle-managed.
- Cardinality monitor history trimmed to 1h; label-value sets capped (F-003); analysis
  offloaded to a thread (F-026).
- Phantom-staleness fixes hold (F-025, F-039).
- Inventory cache: single lock, double-checked TTL, defensive copies (F-078), TTL jitter,
  errors never cached, None-vs-empty for licenses (F-100), filter series pruned (F-079).
- No cross-tier shared-state races found (distinct collector instances per tier; shared
  mutations on the event loop or under locks).
- Webhook path: byte-cap (F-103), constant-time compare (F-109), bounded failure labels
  (F-051), sanitized validation logging (F-166); synchronous → nothing to drain.
- DNS resolver pool design right (F-075/F-076) — growth is the issue, not the pool.
- No FD/thread leaks steady-state (one requests.Session per process; DNS pool fixed at 5).
- Log volume under total failure ~10 error lines/min (measured).
- All lifespan background tasks tracked and cancelled on shutdown.
- `except A, B:` unparenthesized is valid PEP 758 py3.14 — NOT a bug.
- `process_in_batches_with_errors` returns per-item errors; alerts/config receive them.
- Org backoff math correct (exponential from 5 failures, base 60s, cap 3600s).

Regression test worth encoding (from the live harness): start with an invalid API key;
assert /ready stays 503, failure_streak > 0 after N cycles, /health flips 503 after the
staleness threshold.
