# Comprehensive Improvement Roadmap

**Date:** 2026-04-08
**Status:** Approved
**Scope:** Bugs, code consistency, testing, operations, new collectors, and scale optimization
**Target Scale:** 1,000-5,000 devices across multiple organizations with production SLAs
**Approach:** Phased Waves - each wave is independently releasable, ordered by technical risk and value

---

## Wave 1: Foundation Fixes

**Goal:** Eliminate all known bugs and code inconsistencies so subsequent waves build on solid ground.

### 1.1 - Fix Python 2 Exception Syntax (Critical)

5 instances across 4 files use `except X, Y:` (Python 2) instead of `except (X, Y):` (Python 3). This silently catches only the first exception type and assigns the second as the exception variable, meaning some exceptions bypass retry logic entirely.

**Files:**
- `src/meraki_dashboard_exporter/core/error_handling.py` lines 493, 502
- `src/meraki_dashboard_exporter/api/client.py` line 339
- `src/meraki_dashboard_exporter/core/api_helpers.py` line 374
- `src/meraki_dashboard_exporter/core/collector.py` line 454

**Fix:** Replace all with `except (X, Y):` tuple syntax.

### 1.2 - Fix Metric Enum Naming (Medium)

3 POE metrics in `core/constants/metrics_constants.py` lines 99-102 have enum names saying `WATTS` but string values containing `watthours`:

```python
MS_POE_PORT_POWER_WATTS = "meraki_ms_poe_port_power_watthours"
MS_POE_TOTAL_POWER_WATTS = "meraki_ms_poe_total_power_watthours"
MS_POE_NETWORK_TOTAL_WATTS = "meraki_ms_poe_network_total_watthours"
```

**Fix:** Rename enum members to `MS_POE_PORT_POWER_WATTHOURS`, `MS_POE_TOTAL_POWER_WATTHOURS`, `MS_POE_NETWORK_TOTAL_WATTHOURS`. Update all references. This is a breaking change for any code referencing the old enum names - update the changelog and Grafana dashboards (`ms-switches.json`).

### 1.3 - Fix Unbounded Caches (Medium)

Three dictionaries grow indefinitely with every new device serial encountered:

- `DeviceCollector._packet_metrics_cache` (`collectors/device.py:141`) - never cleared
- `MSCollector._last_port_usage` (`collectors/devices/ms.py:38`) - never cleared
- `MSCollector._last_packet_stats` (`collectors/devices/ms.py:39`) - never cleared

**Fix:** Clear entries not seen in the current collection cycle. At the start of each `_collect_impl()`, snapshot the current keys. After collection, evict any keys not updated. This bounds memory to the current device count rather than growing monotonically.

### 1.4 - Resolve Commented-Out `_collect_api_metrics` (Low)

`collectors/organization.py:301` has `# await self._collect_api_metrics(org_id, org_name)` commented out with the note "Skip API metrics for now - it's often problematic."

**Fix:** Investigate the failure mode. If the underlying API endpoint is unreliable, wrap with `@with_error_handling(continue_on_error=True)` and re-enable. If the endpoint is genuinely broken or deprecated, remove the dead method and its metrics entirely.

### 1.5 - Standardize Sub-Collector Patterns (Medium)

Currently 5 different implementations of `_set_metric_value` exist:

1. `core/collector.py` lines 512-588 (base implementation with expiration tracking)
2. `collectors/organization_collectors/base.py` lines 48-79 (delegates to parent via hasattr)
3. `collectors/devices/base.py` lines 219-235 (delegates to parent)
4. `collectors/network_health_collectors/base.py` lines 46-62 (delegates to parent)
5. `collectors/devices/mt.py` lines 254-292 (custom with standalone mode)

**Fix:**
- Consolidate to 2 implementations: the base in `MetricCollector` and a single `SubCollectorMixin` that delegates to parent
- All three base sub-collector classes (`BaseDeviceCollector`, `BaseOrganizationCollector`, `BaseNetworkHealthCollector`) inherit the same delegating mixin
- MTCollector's standalone mode gets its own implementation via the factory pattern (see 1.6)

**Additional standardization:**
- **Initialization:** All sub-collectors call `_initialize_metrics()` in their own `__init__`. Parents do not call it externally.
- **API updates:** All sub-collectors implement `update_api(api)` method. Remove direct `.api = x` assignments in `DeviceCollector._sync_subcollector_api()`.

### 1.6 - Refactor MTCollector Dual Mode (Medium)

`collectors/devices/mt.py` lines 52-61 use `self.parent = None  # type: ignore[assignment]` and a `_standalone_mode` flag to support two operating modes.

**Fix:** Replace with a factory pattern:

```python
class MTCollector(BaseDeviceCollector):
    @classmethod
    def as_subcollector(cls, parent: DeviceCollector) -> MTCollector:
        """Create as a sub-collector of DeviceCollector."""
        return cls(parent=parent)

    @classmethod
    def as_standalone(cls, api: DashboardAPI, settings: Settings, ...) -> MTCollector:
        """Create as an independent collector for MTSensorCollector."""
        instance = cls.__new__(cls)
        instance._init_standalone(api, settings, ...)
        return instance
```

This eliminates `type: ignore`, the `_standalone_mode` flag, and the conditional logic scattered through the class.

### 1.7 - Standardize Error Handling (Low)

Mixed use of `@with_error_handling()` decorator and manual `try/except` across collectors.

**Fix:** Establish and document the convention:
- **`@with_error_handling()`**: All API calls and top-level collection methods. Handles retries, categorization, and metrics.
- **Manual `try/except`**: Only for specific recovery logic that can't be expressed via decorator parameters (e.g., LicenseCollector's 404 fallback to empty state).
- Migrate existing manual handlers in `MSCollector` and others to the decorator where possible.

### 1.8 - Move Port Overview Metrics (Low)

Org-level port aggregate metrics are initialized in `DeviceCollector` coordinator (lines 147-174) but logically belong with `MSCollector`.

**Fix:** Create a `PortOverviewCollector` sub-collector under `MSCollector` (or move directly into `MSCollector._initialize_metrics()`). The coordinator should only coordinate, not own metrics.

### Wave 1 Outcome

Clean, consistent codebase. All known bugs fixed. Sub-collector patterns uniform. No `type: ignore` hacks in collector initialization. Ready to build on.

---

## Wave 2: Test Hardening

**Goal:** Build test confidence sufficient to ship infrastructure and feature changes safely at scale.

### 2.1 - Add Coverage Threshold Gate (High)

- Add `--cov-fail-under=80` to pytest invocation in `.github/workflows/ci.yml`
- Configure Codecov PR comments in `codecov.yml` so coverage diffs are visible on every PR
- Starting threshold: 80%. Increase incrementally as new tests land.

### 2.2 - Error Scenario Test Suite (High)

Expand coverage for error paths critical at scale:

- **Rate limiting (429):** Use `MockAPIBuilder.with_sequential_responses()` to simulate 429 -> 429 -> 200. Verify exponential backoff timing, jitter application, and eventual success.
- **Server errors (500/502/503):** Verify retry behavior with `max_retries=3`. Verify correct `ErrorCategory` assignment.
- **Timeouts:** Verify collector timeout (120s default) triggers clean cancellation via `asyncio.wait_for`. Verify partial results are not persisted.
- **API unavailable:** Verify `APINotAvailableError` propagation, collector health counter increment, and graceful degradation.

### 2.3 - Async Edge Case Tests (Medium)

Cover concurrency scenarios that surface at 1K+ devices:

- **ManagedTaskGroup cancellation:** Start 10 tasks, cancel the group after 3 complete. Verify remaining tasks are cancelled, completed tasks' results are preserved, cleanup runs.
- **Semaphore exhaustion:** Create ManagedTaskGroup with `max_concurrency=2`, submit 10 tasks. Verify only 2 run concurrently (measure via timestamps).
- **Rate limiter contention:** Run 20 concurrent `OrgRateLimiter.acquire()` calls with `rate=5/s`. Verify throughput stays within bounds.
- **Collection cycle overlap:** Simulate a MEDIUM collector that takes 400s (exceeding 300s interval). Verify the next cycle is skipped or queued, not stacked.

### 2.4 - Integration Test Expansion (Medium)

Currently 2 integration test files. Add:

- **Full collection cycle:** Wire `CollectorManager` with mock API. Run one complete FAST + MEDIUM + SLOW cycle. Verify all expected metrics appear with correct labels and reasonable values.
- **Metric expiration:** Set a device metric, advance time past TTL, run expiration cleanup. Verify the metric's label set is removed.
- **Inventory cache integration:** Run two collectors that both call `inventory.get_devices(org_id)`. Verify second call is a cache hit (check counter).
- **Multi-org:** Configure 2 organizations. Run collection. Verify label isolation (org_id labels don't cross-contaminate).

### 2.5 - Large-Scale Test Improvements (Low)

- Add a weekly CI schedule that includes `@pytest.mark.slow` tests
- Expand large org fixture to include all device types (MR, MS, MX, MV, MG, MT)
- Add parameterized device collector tests using `@pytest.mark.parametrize` over device types to reduce duplication across the 5 separate test files

### Wave 2 Outcome

Coverage gate enforced in CI. Error and retry paths validated. Async concurrency tested. Confidence to ship Waves 3-5 safely.

---

## Wave 3: Operational Readiness

**Goal:** Production-grade for 1K-5K devices in Kubernetes with SLAs.

### 3.1 - Readiness Probe Endpoint (High)

Add `GET /ready` to FastAPI:

- Returns `503 Service Unavailable` until the first complete collection cycle finishes (at least one FAST + one MEDIUM cycle)
- Returns `200 OK` with `{"ready": true, "collectors": {"fast": true, "medium": true, "slow": false}}` once ready
- Track readiness state in `CollectorManager` via `_tier_initial_complete: dict[UpdateTier, bool]`
- `/health` remains unchanged (liveness = process alive)
- `/ready` = process has data to serve

**Why this matters:** Without a readiness probe, Kubernetes marks the pod as ready immediately. Prometheus scrapes an empty `/metrics` during the 60-300s startup window, causing false alerts on "missing metrics."

### 3.2 - Kubernetes / Helm Chart (High)

Create `charts/meraki-dashboard-exporter/`:

- **Deployment:** Single replica (not horizontally scalable due to Meraki API rate limits per org). Configurable via values.
- **Probes:** `livenessProbe` on `/health` (30s interval, 10s timeout). `readinessProbe` on `/ready` (10s interval, 5s timeout, 300s initialDelaySeconds).
- **Secret:** For `MERAKI_EXPORTER_MERAKI__API_KEY`. Support both inline value and `existingSecret` reference.
- **ConfigMap:** For non-sensitive env vars (org ID, intervals, concurrency, OTEL config).
- **ServiceMonitor:** For Prometheus Operator autodiscovery. Configurable scrape interval.
- **Security context:** Non-root (UID 1000), read-only filesystem, drop all capabilities, no privilege escalation. Matches existing Docker hardening.
- **Resources:** Default requests `cpu: 100m, memory: 256Mi`, limits `cpu: 500m, memory: 512Mi`. Documented sizing guidance for different scales.
- **Values:** Sensible defaults with inline documentation comments.

### 3.3 - Metric Expiration Tier Tracking (Medium)

Address TODO at `core/metric_expiration.py:228`:

- Extend `track_metric_update()` signature to accept `tier: UpdateTier`
- Store tier alongside timestamp in `_metric_timestamps`
- Apply tier-specific TTLs during cleanup:
  - FAST: `2 * 60s = 120s`
  - MEDIUM: `2 * 300s = 600s`
  - SLOW: `2 * 900s = 1800s`
- Fallback to current default TTL if tier is not provided (backwards compatible)

### 3.4 - API Client Type Safety (Medium)

Remove `# mypy: disable-error-code="no-any-return"` from `api/client.py`:

- Create typed wrapper methods for each Meraki SDK call used by collectors
- Return types as `TypedDict` for simple responses, Pydantic models for complex ones
- Gradual migration: start with the most-used endpoints (device status, org inventory), expand over time
- This catches type errors at development time, especially valuable as Wave 4 adds new API integrations

### 3.5 - Log Aggregation Examples (Low)

Add to `docs/deployment-operations.md`:

- Grafana Alloy config snippet for shipping structlog logfmt output to Loki
- Note on available formats (`logfmt` default, `json` via `MERAKI_EXPORTER_LOGGING__FORMAT=json`)
- Example LogQL queries: collector failures, rate limit events, slow collections

### 3.6 - Graceful Degradation on Partial API Failures (Medium)

Formalize per-org error isolation:

- If one organization's API calls fail, other orgs continue collecting normally
- New metric: `meraki_exporter_org_collection_status` (gauge, 1=success, 0=failed) per org_id, org_name
- After N consecutive failures (configurable, default 5) for an org, exponentially back off that org's collection frequency
- Recovery: On first success after backoff, immediately resume normal interval
- Log backoff/recovery transitions at WARNING level

### Wave 3 Outcome

Kubernetes-ready with proper health semantics. Metric expiration is tier-aware. Type safety improved. Graceful degradation under partial failures.

---

## Wave 4: New Collectors

**Goal:** Expand monitoring coverage. Each collector follows established patterns: enum metrics in `metrics_constants.py`, `@register_collector` or sub-collector pattern, inventory caching, `@with_error_handling`, Pydantic domain models, unit tests, dashboard updates.

### 4.1 - VPN/WAN Health Collector (High)

Major visibility gap for site-to-site VPN at scale.

- **API endpoints:** `getOrganizationApplianceVpnStatuses`, `getOrganizationApplianceVpnStats`
- **Metrics:**
  - `meraki_mx_vpn_peer_status` (gauge, 1/0) - labels: org_id, org_name, network_id, network_name, peer_network_id, peer_type
  - `meraki_mx_vpn_latency_ms` (gauge) - per peer
  - `meraki_mx_vpn_jitter_ms` (gauge) - per peer
  - `meraki_mx_vpn_packet_loss_ratio` (gauge) - per peer
  - `meraki_mx_vpn_peers_total` (gauge) - per network
- **Tier:** MEDIUM (300s)
- **Implementation:** Sub-collector under `MXCollector`
- **Dashboard:** New panel group in `mx-security-appliances.json`

### 4.2 - Switch Stack & Hardware Health Collector (High)

Switch stack splits and hardware failures are common at scale.

- **API endpoints:** `getNetworkSwitchStacks`, `getNetworkSwitchStackRoutingInterfaces`. Note: Meraki API may not expose dedicated PSU/fan/temperature endpoints for MS switches - investigate `getOrganizationDevicesStatuses` and `getDevice` response fields for hardware health data. If unavailable via API, scope this collector to stack status only and document the gap.
- **Metrics (confirmed available):**
  - `meraki_ms_stack_member_status` (gauge) - labels: stack_id, serial, role (primary/secondary/member)
  - `meraki_ms_stack_members_total` (gauge) - per stack
- **Metrics (pending API investigation):**
  - `meraki_ms_power_supply_status` (gauge, 1/0) - per serial, psu_id
  - `meraki_ms_fan_status` (gauge) - per serial
  - `meraki_ms_temperature_celsius` (gauge) - per serial, sensor_location
- **Tier:** MEDIUM (300s)
- **Implementation:** Sub-collector under `MSCollector`
- **Dashboard:** New panel group in `ms-switches.json`

### 4.3 - Firewall & Security Policy Collector (Medium)

Tracks configuration drift and security events.

- **API endpoints:** `getNetworkApplianceFirewallL3FirewallRules`, `getNetworkApplianceFirewallL7FirewallRules`, `getOrganizationApplianceSecurityEvents`
- **Metrics:**
  - `meraki_mx_firewall_rules_total` (gauge) - per network, rule_type (L3/L7)
  - `meraki_mx_firewall_default_policy` (info) - per network
  - `meraki_mx_security_events_total` (counter) - per network, event_type
- **Tier:** SLOW (900s)
- **Implementation:** Sub-collector under `MXCollector`
- **Dashboard:** New panel group in `mx-security-appliances.json`

### 4.4 - Per-SSID Performance Collector (Medium)

RF health exists but per-SSID client experience is missing.

- **API endpoints:** `getNetworkWirelessClientCountHistory`, `getNetworkWirelessLatencyStats`, `getNetworkWirelessFailedConnections`
- **Metrics:**
  - `meraki_mr_ssid_client_count` (gauge) - per network, ssid, band
  - `meraki_mr_ssid_latency_ms` (histogram) - per network, ssid. Buckets: [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]
  - `meraki_mr_ssid_failed_connections_total` (counter) - per network, ssid, failure_step (auth/assoc/dhcp/dns)
  - `meraki_mr_ssid_retry_rate_ratio` (gauge) - per network, ssid, band
- **Tier:** MEDIUM (300s)
- **Implementation:** Sub-collector under `NetworkHealthCollector`
- **Dashboard:** New panel group in `network-health-performance.json`

### 4.5 - Webhook Event Metrics Collector (Low)

Convert existing webhook handler events into metrics.

- **Approach:** Event-driven, not polled. The existing webhook handler writes to this collector's metrics on each received event.
- **Metrics:**
  - `meraki_webhook_events_total` (counter) - per event_type, network_id, alert_type
  - `meraki_webhook_last_event_timestamp` (gauge) - per event_type
  - `meraki_webhook_processing_errors_total` (counter) - per error_type
- **Tier:** N/A (event-driven)
- **Implementation:** `WebhookMetricsCollector` registered outside the tier system. Webhook handler calls `collector.record_event()` on each push.
- **Dashboard:** New panels in `assurance-alerts.json`

### Wave 4 Outcome

Comprehensive monitoring: VPN health, hardware status, security policy, wireless performance, real-time webhook events. All following established patterns with tests and dashboards.

---

## Wave 5: Scale & Polish

**Goal:** Optimize for 1K-5K devices and prepare for growth beyond.

### 5.1 - Collection Batching & Parallelism Tuning (High)

At 1K+ devices, serial per-device API calls become the bottleneck.

- **Batch API calls:** Audit each collector for per-device calls that have org-wide equivalents (e.g., `getOrganizationDevicesStatuses` returns all devices in one call). Prefer org-wide endpoints.
- **Intra-collector parallelism:** Standardize `ManagedTaskGroup` usage within collectors that must make per-network/per-device calls.
- **Per-tier concurrency:** Replace global `api.concurrency_limit` with per-tier settings:
  - `api.concurrency_limit_fast` (default: 5) - sensor readings are lightweight
  - `api.concurrency_limit_medium` (default: 3) - standard collection
  - `api.concurrency_limit_slow` (default: 2) - config endpoints are heavier
- **Target:** 2-5x reduction in MEDIUM tier collection duration for 1K+ device orgs

### 5.2 - Inventory Cache Smartening (Medium)

TTL-based caching with fixed expiration causes unnecessary API calls at scale.

- **Staggered refresh:** Add jitter to cache TTLs (TTL +/- 10%) to prevent thundering herd on simultaneous cache expiry
- **Cache warming:** Pre-populate inventory cache on startup before starting collectors. First collection cycle should be cache hits, not misses.
- **Event-driven invalidation:** When a collector encounters an unknown device serial, invalidate the device inventory cache for that org.
- **Cache metrics:** `meraki_exporter_inventory_cache_size` (gauge) per org_id, cache_type (devices/networks/availability)

### 5.3 - Metric Cardinality Controls (High)

At 5K devices with per-port/per-client metrics, cardinality can explode.

- **Configurable limits:** `MERAKI_EXPORTER_MONITORING__MAX_CARDINALITY_PER_COLLECTOR` (default: 10000)
- **Automatic shedding:** When exceeding budget, drop least-recently-updated label sets (integrates with expiration manager)
- **Alert metric:** `meraki_exporter_cardinality_limit_reached` (gauge, 1/0) per collector
- **Dashboard:** Cardinality panel in `exporter-monitoring.json`

### 5.4 - API Call Reduction Audit (Medium)

Systematic audit of every API call:

- Map every `asyncio.to_thread(api.xxx)` call to its Meraki endpoint
- Identify overlapping data fetches (e.g., device status in both DeviceCollector and inventory)
- Replace per-device calls with org-wide equivalents where available
- Document remaining per-device calls with justification
- **Target:** 30-50% reduction in total API calls per collection cycle

### 5.5 - Collection Smoothing Refinement (Low)

Refine the existing smoothing system:

- **Adaptive window:** If a cycle completes faster than expected, tighten smoothing. If slower, widen it.
- **Priority scheduling:** Collectors that complete in <5% of their interval skip smoothing entirely.
- **Utilization metric:** `meraki_exporter_collection_utilization_ratio` (gauge) = actual_duration / interval, per collector. Values approaching 1.0 indicate the collector can't keep up.

### 5.6 - Documentation & Dashboard Refresh (Low)

Final polish:

- Update all Grafana dashboards with Wave 4 metrics
- Run `make docgen` to regenerate auto-generated docs
- Add "Scaling Guide" to `docs/` with recommendations for 100, 1K, and 5K device deployments
- Add runbook entries: rate limit exhaustion, collector timeouts, cardinality spikes, org-level backoff

### Wave 5 Outcome

Collection 2-5x faster at scale. API calls reduced 30-50%. Cardinality bounded. Dashboards and docs complete. Ready for 5K+ growth.

---

## Wave Dependencies

```
Wave 1 (Foundation) ──> Wave 2 (Testing) ──> Wave 3 (Operations) ──> Wave 4 (Collectors) ──> Wave 5 (Scale)
                                                                 └──> Wave 5 (Scale)
```

- Waves 1 -> 2: Tests need clean code patterns to test against
- Waves 2 -> 3: Operational changes need test coverage to validate
- Waves 3 -> 4/5: New collectors and scale work need operational infrastructure (readiness probe, Helm, type safety)
- Waves 4 and 5 can run in parallel once Wave 3 is complete

## Items Per Wave Summary

| Wave | Items | Priority Breakdown |
|------|-------|-------------------|
| 1: Foundation | 8 items (1.1-1.8) | 1 critical, 4 medium, 3 low |
| 2: Testing | 5 items (2.1-2.5) | 2 high, 2 medium, 1 low |
| 3: Operations | 6 items (3.1-3.6) | 2 high, 3 medium, 1 low |
| 4: Collectors | 5 items (4.1-4.5) | 2 high, 2 medium, 1 low |
| 5: Scale | 6 items (5.1-5.6) | 2 high, 2 medium, 2 low |
| **Total** | **30 items** | |
