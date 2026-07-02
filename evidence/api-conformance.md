# API-conformance lane reports (org/network + device fetchers)

Produced 2026-07-02 by the v1-readiness assessment against OpenAPI spec v1.72.0 (670
paths) + installed Meraki SDK 3.3.0. Backs issues #512–#527, #548–#557, #611, #612.
KEY LESSON (live-verified): **the spec is not always right** — see
`live-api-verification.md` for the channel-utilization case where the live wire format
contradicts the spec schema. Always confirm live before scaling/renaming field reads.

## APIORG — org/network-side per-fetcher verdicts

organization.py: getOrganizationDevicesOverviewByModel L680 OK (networkIds-scoped,
counts/items shapes handled) · getOrganizationDevicesAvailabilities L775 fallback OK ·
getOrganizationDevicesPacketCaptureCaptures L872 OK (perPage=3 meta-only by design) ·
getOrganizationSummaryTopApplicationsCategoriesByUsage L992 OK (quantity clamped 50).
organization_collectors: api_usage L59 OK (timespan=3600) · client_overview L60 OK
(usage in kb MATCHES spec — do not rescale) · device_availability_history L60 OK ·
firmware L61 OK · license L53/L92 → #516/#526.
network_health_collectors: air_marshal L103 → #612 (spec now has bounded
encryption[WEP/WPA/open] + types[rogue/spoof] enums; module docstring stale) · bluetooth
L47 OK (perPage=1000 max) · connection_stats L46 OK (timespan 1800 ≤ 604800 — NOTE this
endpoint's cap is 7 days, tighter than the usual 2678400) · data_rates L47 OK ·
latency_stats L104/L137 OK (+#555: pass fields="avg" to skip unused rawDistribution) ·
rf_health L124 → #512 · ssid_performance L53 OK.
alerts.py: getOrganizationAssuranceAlerts L340 OK but perPage unset (default 30 vs max
300) → #548 · _fetch_networks_direct L567 OK (reapplies NetworkFilter) ·
getNetworkSensorAlertsOverviewByMetric L606 OK · single-org getOrganization L302
unwrapped → #519 · unknown severities dropped → #524.
clients.py: getNetworkClients L463 OK (perPage=5000 max, total_pages=all) ·
applicationUsage L941 OK but 1000-ID GET batch → #525 · signalQualityHistory L1121 OK.
config.py: getOrganizationLoginSecurity L280 OK (but bypasses the inventory cache →
#551; strong-passwords field deprecated-always-true → #523) · getOrganizationAdmins L390
OK (genuinely non-paginating — no total_pages kwarg exists) ·
getOrganizationConfigurationChanges L472 — rows NOT filtered by get_allowed_network_ids
→ #513 (fatal-rule violation; alerts.py:424-425 is the correct pattern; keep
networkId=None org-level rows) · single-org getOrganization L219 unwrapped → #519.
services/inventory.py: networks L469 / devices L593 / availabilities L705 / licenses
L1031+L1124 / login-security L1214 all OK (total_pages=all, filter-on-read, defensive
copies) · get_login_security is DEAD CODE (zero prod callers) → #551 · getOrganizations
L386 lacks total_pages=all (perPage default 9000 — consistency only) → #557.
core/api_helpers.py: _fetch_networks_direct L178 OK (reapplies filter, tested) ·
_fetch_devices_direct L257-300 does NOT reapply NetworkFilter (latent — fires only when
inventory is None) + product_types filter asymmetry → #520.
core/discovery.py: unfiltered by design (audit-only) ✔; single-org branch unwrapped →
#522. core/org_health.py, client_store, dns_resolver: no Meraki fetchers.
api/client.py: SDK config sane (wait_on_rate_limit=True, retry_4xx_error=False,
maximum_retries from settings, single_request_timeout=30 → #556 for large orgs).

Licensing (#516, TRIPLE-corroborated): license.py L150 branches co-term
(licensedDeviceCounts) vs per-device; Meraki has THREE models — subscription orgs fall
through to per-device, getOrganizationLicenses 400s ("does not support per-device
licensing"), only "404" is special-cased (L183) → zero license metrics + retry noise +
**org_collection_status=0 permanently** (record_failure every cycle) for a healthy org.
Fix (b) preferred: when licensedDeviceCounts absent, use the overview's own
states.{active,expiring,expired}.count (already fetched) — covers per-device AND
subscription orgs and avoids the 400 entirely. Verification still needed against a real
subscription org (Rob's homelab is co-term).

## APIDEV — device-side per-fetcher verdicts

HEADLINE: no P0/P1; pagination clean everywhere (every paginated endpoint passes
total_pages="all"); all 36 SDK methods exist; validate_response_format on all 40 fetchers
with correct expected_type.

| File:line | SDK method | Verdict |
|---|---|---|
| device.py:1272 | getOrganizationDevicesAvailabilities | OK |
| devices/base.py:107 | getOrganizationDevicesSystemMemoryUsageHistoryByInterval | perPage unset (default 10, max 20) → #548; ×1024 for kB → #531 note |
| devices/mg.py:154 | getOrganizationCellularGatewayUplinkStatuses | OK |
| devices/mr/clients.py:140 | getNetworkWirelessDevicesConnectionStats | OK (per-network fan-out) |
| devices/mr/clients.py:208 | getOrganizationWirelessClientsOverviewByDevice | OK |
| devices/mr/performance.py:455/894/923/1030 | ethernet/packet-loss×2/CPU | OK (perPage/timespan at spec bounds) |
| devices/mr/wireless.py:194/320 | SSID statuses byDevice / top-SSIDs | OK (perPage=500 max; quantity=50 max; MB units match _mb names) |
| devices/ms_power.py:96 | getOrganizationDevicesPowerModulesStatusesByDevice | OK (spec types `network` as bare object; live is {"id": ...} — see #508) |
| devices/ms.py:757/844/1033/1223/1237/1488/1594/1736 | switch port suite | OK except ×1024-vs-×1000 (usageInKb ×1024 but trafficInKbps ×1000/8 in the SAME functions — standardize ×1000 for data volume, memory KiB defensible) → #531 |
| devices/mt.py:240/306/342 | sensor readings/gateways | OK (but undecorated for rate limiter + all-serials param → #553) |
| devices/mv.py:219/268 | getDeviceCameraAnalyticsZones / AnalyticsLive | **BOTH DEPRECATED in v1.72.0** → #549 (QualityAndRetention L316 NOT deprecated) |
| devices/mx_firewall.py:161/193/249 | L3/L7 rules, security events | OK |
| devices/mx_ha.py:110 | redundancy byNetwork | OK |
| devices/mx_uplink_health.py:98 | uplinksLossAndLatency | last-write-wins across per-destination-IP rows → #517 (aggregate max per serial+interface) |
| devices/mx_uplink_usage.py:99 | uplinksUsageByNetwork | OK |
| devices/mx_vpn.py:122/225 | vpn statuses/stats | OK (stats timespan=300 may yield sparse summaries → #527) |
| devices/mx.py:171/217 | appliance performance / uplink statuses | perf lacks timespan → #521; uplinks OK |
| mt_alerts.py:274 | sensorAlertsCurrentOverviewByMetric | OK |

## apidrift tool assessment

tools/apidrift is mature + CI-wired: AST-scans consumed operationIds, diffs live-vs-
vendored spec, checks Pydantic models against live 2xx schemas via opt-in `__meraki_op__`
annotations; exit codes 0/2/3 gate CI. Automates response-shape drift + endpoint-vanished
for annotated models. Does NOT cover: pagination correctness, timespan/perPage bounds,
unit interpretation (kB vs KiB), aggregation semantics (#517-class). → #609 expands
annotation coverage; #508 fixes the current false-positive (submodel vs bare-object).

## Ruled out (do not re-flag)

- Silent pagination truncation at 500-net/5k-device scale: NONE found — every genuinely
  at-risk bulk endpoint passes total_pages="all".
- Unit bugs beyond those listed: client_overview kb correct; data_rates
  kilobytes-per-second already documented (F-065 — the NAME is the bug, → #531).
- validate_response_format correctly ABSENT where payloads are {items/meta}-wrapped
  (packet-captures, device-overview-by-model) — inline errors-checks there are correct;
  wrapping them would mis-unwrap.
- NetworkFilter law held everywhere except #513/#520; rf_health's direct
  getOrganizationDevices fallback is scoped to a single pre-filtered network (not a bypass).
- No deprecated operationIds in use EXCEPT the two MV analytics calls (#549).
- `except TypeError, ValueError:` is valid PEP 758 on py3.14 — not a bug.
- NetworkClient.usage.total handled via extra="allow" (spec gap, not a bug).
