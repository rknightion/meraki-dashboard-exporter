# SCALE lane report — API budget, scale & capacity analysis

Produced 2026-07-02 by the v1-readiness assessment (Fable lane, four file-complete
sub-audits covering all 34+ SDK call sites; every P0/P1 mechanism independently
re-verified in source). Backs issues #540–#557, #270 (comment), #271 (comment), #542,
#617. Reference scales — SMALL: 1 org / 10 nets (6 wireless) / 100 devices.
LARGE-1org (university): 1 org / 500 nets (400 wireless, 100 switch-nets, 100
appliance-nets, 50 sensor-nets) / 5,000 devices (4,000 MR, 700 MS, 150 MX, 100 MV, 50 MT).

## 1. Scheduling model (verified)

- Three independent tier loops (`app.py:391-487`) run concurrently and DO overlap; the
  only cross-tier coordination is the single shared `OrgRateLimiter` (`manager.py:78`,
  injected into every collector and into `OrganizationInventory`). Per-collector
  `asyncio.Lock` prevents same-collector overlap (`manager.py:652`); collector timeout
  default 240s; tier intervals 60/300/900s.
- Tier membership (verified via `@register_collector`): FAST(60s): MTSensorCollector.
  MEDIUM(300s): DeviceCollector, NetworkHealthCollector, OrganizationCollector,
  AlertsCollector, MTSensorAlertsCollector, ClientsCollector (gated on `clients.enabled`,
  default False). SLOW(900s): ConfigCollector.
- Client-side limiter: per-org token bucket, default 10 rps × `rate_limit_shared_fraction=1.0`,
  burst 20 (`core/rate_limiter.py:42-46`). Acquired in `@log_api_call`
  (`core/logging_decorators.py:65-67`), in inventory (`services/inventory.py:167`), and
  manually in `clients.py`. Meraki-side limit: 10 req/s per org (spec v1.72.0 documents
  special limits only on liveTools endpoints — exporter calls none). SDK layer retries
  429s (`wait_on_rate_limit=True`, `maximum_retries=3`, `api/client.py:150-164`).
- Inventory cache TTLs (`services/inventory.py:59-69`): orgs/networks/devices 900s;
  availabilities 120s (→ real refetch every MEDIUM cycle); licenses 1800s; login-security
  3600s. `warm_cache()` warms orgs+networks+devices at startup.

## 2. Per-collector call formulas (steady state)

O=orgs, W=wireless nets, Sn=sensor nets, Sw=switch nets, A=appliance nets; "call" = one
logical SDK call; pagination multipliers listed below the table.

| Collector (tier) | Calls per cycle | Key call sites |
|---|---|---|
| MTSensor (60s) | 2×O (`getOrganizationSensorReadingsLatest` + `...SensorGatewaysConnectionsLatest`) | `devices/mt.py:305,342` |
| Device (300s) | ~20 org-wide/org + 1×W (MR conn-stats loop) + 1×Sw (stacks) + Sw/3 (STP, 900s gate) + 2A/3 (MX firewall, 900s gate) + ⌈MR/20⌉ (CPU history batches) + 1×MV camera (analytics live) + 2MV/3 (MV config, 900s gate) + 1×physical-MX (`getDeviceAppliancePerformance`) + MS/2 (per-switch packet stats, 600s gate) | `device.py`; `ms.py:757,1223,1594`; `mr/clients.py:140`; `mr/performance.py:1030`; `mv.py:219,268,316`; `mx.py:171` |
| NetworkHealth (300s) | **8×W** — channel-util, conn-stats, data-rates, bluetooth, failed-conns, device-latency, client-latency, air-marshal; per wireless network, EVERY cycle, no interval gating | bundle `network_health.py:349`; `rf_health.py:123`, `connection_stats.py:45`, `data_rates.py:46`, `bluetooth.py:46`, `ssid_performance.py:52`, `latency_stats.py:103,136`, `air_marshal.py:102` |
| Organization (300s) | ~8×O uncached/cycle (model-overview, packet-captures perPage=3, app-usage, api-usage, client-overview, availability-history, firmware, availabilities@TTL120) | `organization.py:679,871,991`; `organization_collectors/*` |
| Alerts (300s) | O + Sn (org-wide assurance alerts + per-sensor-network overview) | `alerts.py:339,605` |
| MTSensorAlerts (300s) | Sn | `mt_alerts.py:273` |
| Config (900s) | 3×O | `config.py:279,389,471` |
| Clients (300s, OFF by default) | N (`getNetworkClients` perPage=5000) + N×⌈clients/1000⌉ per 600s (app usage) + N×min(wireless clients,200) per 600s single-client signal-quality calls | `clients.py:463,940,1120` |

Pagination multipliers that matter (perPage maxima verified vs spec v1.72.0): org
memory-usage-history max perPage 20, SDK default 10, **code sets none** → 500 HTTP
pages/org/cycle at 5,000 devices (`devices/base.py:106-112`); MS port-statuses-by-switch
perPage=20 (endpoint max) → ⌈MS/20⌉ pages; assurance alerts default 30 (max 300, code
sets none).

## 3. Capacity table (req/s incl. pagination; clients collector OFF)

| Load source | SMALL | LARGE-1org | LARGE split 5 ways |
|---|---|---|---|
| NetworkHealth (8×W/300s) | 0.16 rps | **10.7 rps** | 10.7 (2.1/org) |
| Device (incl. 500 memory pages, 350 MS packet, 400 MR conn-stats, 200 CPU batches, 167 MV, 150 MX-perf) | 0.21 | **~6.7** | ~6.7 (1.3/org) |
| Organization + Alerts + MTAlerts + Config + FAST | 0.06 | ~0.4 | ~0.5 |
| **Total demand** | **~0.43 rps ≈ 4% of the 10 rps org budget** | **~17.8 rps ≈ 178% of the org budget** | ~3.6 rps/org (36%) but see the global-bucket ceiling (#270 comment) |
| Requests/day | ~37k | ~1.5M demanded | ~1.5M |

**Wall-clock feasibility at LARGE-1org:** NetworkHealth alone needs 3,200 calls/cycle;
even granted the org's ENTIRE 10 rps budget that is ≥320s > the 240s collector timeout →
times out every cycle. DeviceCollector (~2,000 calls) contends in the same MEDIUM window
(tier concurrency 3) → both starve. **Practical single-org envelope with current
defaults: roughly ≤150–200 wireless networks and ≤1,500–2,000 devices — and that assumes
the customer cedes the whole org API budget to the exporter.**

## 4. Findings (filed as issues; full text in findings-synthesis.md)

- SCALE-01 → #540 (P0): shared 10k `max_cardinality_per_collector` keyed
  `collector_name="DeviceCollector"` for ALL device sub-collectors; sheds LIVE series via
  `Gauge.remove` (`core/metric_expiration.py:322-368`, `core/collector.py:646-652`) from
  ~10 48-port switches (~1,100 tracked series each) or ~600 MR APs (~15/AP) upward;
  permanent shed/re-create flapping at scale.
- SCALE-02 → #541 + #271-comment (P0): 8 calls/wireless-net/300s unrunnable at 400 W.
- SCALE-03 → #542 (P1): aggregate demand 178% of budget; sizing formula must ship.
- SCALE-04 → #270-comment (P1): limiter porous 3 ways — (a) one token per decorated
  METHOD not per HTTP request (pagination/loops under one token); (b) network_id/serial-
  first fetchers mis-keyed to the shared global bucket (`logging_decorators.py:398-401`;
  affected: `rf_health.py:104`, both `latency_stats.py` fetchers, `air_marshal.py:102`,
  `mv.py:219,268,316`, `mt_alerts.py:273`) → single org can draw ~20 rps outbound;
  (c) undecorated sites acquire nothing (`ms.py:1488`, `mr/performance.py:922`,
  `mt.py:305`). Only 4 of the 8 network-health fetchers got the F-170 org_id threading.
- SCALE-05 → #543/#542 (P1): multi-GB RSS at LARGE vs published 512Mi sizing (registry
  0.6–1.1M series clients-off; ClientStore no global cap; DNS caches unbounded;
  CardinalityMonitor retains full label lists).
- SCALE-06 → #533 (P1): client metrics via raw `.labels().set()` (never expiration-
  tracked), hostname/description attacker-influenced, app-usage uncapped, signal-quality
  1 call/client (80k calls/600s at scale).
- SCALE-07 → #549; SCALE-08 → #552; SCALE-09 → #271-comment (org-wide
  `getOrganizationWirelessDevicesChannelUtilizationByDevice/ByNetwork` exist, perPage max
  1000; NO org-wide equivalents exist for conn-stats/failed-conns/data-rate/latency/
  air-marshal — those need interval gating); SCALE-10 → #548; SCALE-11 → #541;
  SCALE-12 → #550; SCALE-13 → #553; SCALE-14 → #543; SCALE-15 → #554; SCALE-16 → #544;
  SCALE-17 → fixed in devices/CLAUDE.md (commit f08cd69).

## 5. Checked and found OK (do not re-flag)

- SMALL scale comfortably safe (~0.43 rps, registry ~20–50k series, RSS < 256Mi).
- Tier loops don't self-overlap (per-collector lock + skip, `manager.py:652-658`);
  timeout 240s < interval 300s prevents runaway stacking.
- Startup deliberately avoids a burst: discovery + sequential tier-by-tier initial
  collection (`manager.py:454-479`, `app.py:340-360`); readiness withheld until real
  success (F-105).
- Inventory service rate-limited + org-keyed on every call, TTL jitter ±10%,
  `warm_cache()` makes first-cycle reads hits; availabilities TTL 120s is intentional.
- MS port collection default path correct: org-level endpoints (F-168) with per-device
  probe-gated fallback; perPage already at spec maxima (20/50/20).
- Per-endpoint interval gates exist where implemented (ms_port_usage_interval /
  ms_packet_stats_interval / client_app_usage_interval / client_signal_quality_interval
  = 600s; MX firewall + MV config + MS STP on 900s gates) — the pattern just needs
  extending.
- Alerts: per-network `getNetworkHealthAlerts` loop already removed (F-064); sensor
  fan-out restricted to sensor networks.
- OrgHealthTracker backoff gates six collectors per org (F-169) — but see #547.
- Rate-limiter self-metrics are real series (F-028/F-074).
- The org_id keying heuristic works for org-first fetchers (numeric isdigit()); failures
  are exclusively network_id/serial-first fetchers.
- `except TypeError, ValueError:` is valid PEP 758 on py3.14 — NOT a bug (verified
  ast.parse; confirmed three times by independent lanes — do not "fix").
- No liveTools / special-rate-limit endpoints called.
- `docs/api-call-audit.md` is directionally accurate for the small case only; its
  assumptions hide every finding above. `docs/scaling-guide.md` qualitative advice is
  sound; its numbers (512Mi, cardinality 25k) are not.
