# MET lane report — Prometheus metric-contract audit

Produced 2026-07-02 by the v1-readiness assessment. Scope: 253 metric-name strings —
238 `*MetricName` enum values in `core/constants/metrics_constants.py` + 15 hardcoded
literals. Docs (`docs/metrics/metrics.md`) are code-generated and byte-reproducible —
zero drift (verified by regenerating + diffing), so every rename below auto-propagates
via `make docgen`. Backs issues #531–#539 and #533. Rob's decision (2026-07-02):
**rename now, pre-1.0, no dual-emit** (#531).

## Type reality

Almost every data metric is a Gauge. The ONLY Counters are exporter self-metrics + DNS +
webhook counters (all correctly `_total`-suffixed except the two flagged under #532).
Histograms: collector/rate-limiter/webhook durations (correct).

## Compact family table (grouped by owner; ⚠ = finding applies)

ORGANIZATION collector (MEDIUM), organization.py:
- meraki_org (Info → exposed as meraki_org_info ✔) [org]
- meraki_org_api_requests_total (G) — ⚠ 1-HOUR WINDOW named _total (flagship MET-02 case)
- meraki_org_api_requests_by_status (G, +status_code) — windowed
- meraki_org_networks_total / _devices_total / _devices_by_model_total(+model) /
  _devices_availability_total(+product_type/status) (G) — ⚠ snapshot counts named _total
- meraki_org_clients_total (G) — windowed ⚠
- meraki_org_usage_total_kb / _downstream_kb / _upstream_kb (G) — ⚠ _kb + _total
- meraki_org_application_usage_total_mb / _downstream_mb / _upstream_mb / _percentage
  (G, +category) — ⚠ _mb + _percentage
- meraki_org_packetcaptures_total / _remaining (G) ⚠
- meraki_org_licenses_total(+license_type/status) / _licenses_expiring (G) ⚠
- meraki_org_devices_availability_changes_total (G) — windowed ⚠
- meraki_org_firmware_upgrades_total / _pending_total (G) ⚠

CONFIG collector (SLOW), config.py — all (G) [org]:
- meraki_org_login_security_* (14 gauges; ⚠ *_idle_timeout_minutes, *_password_expiration_days
  non-base units)
- meraki_org_configuration_changes_total (G) — ⚠ WINDOWED named _total
- meraki_org_admins_total / _admins_two_factor_enabled_total (G) ⚠

DEVICE (MEDIUM), device.py: meraki_device_up (G ✔), meraki_device_status_info (info ✔),
meraki_device_memory_{used,free,total}_bytes (✔), meraki_device_memory_usage_percent.

MS (devices/ms.py): meraki_ms_port_status/_port_traffic_bytes(=bytes/SEC rate!)/_port_usage_bytes/
_port_client_count; _port_error_active/_warning_active (✔ deliberately no _total, F-091);
meraki_ms_port_packets_{total,broadcast,multicast,crcerrors,fragments,collisions,
topologychanges} (G, +direction) — ⚠ 5-MIN WINDOW named _total; _port_packets_rate_* — ⚠
_rate_total; meraki_ms_ports_active_total/_inactive_total/_by_media_total/_by_link_speed_total ⚠;
power: _power_usage_watts ✔, _poe_budget_watts ✔, _poe_*_watthours ⚠ (energy → joules?);
_stp_priority, _port_stp_state, _port_8021x_*, _power_supply_status, _stack_member_status,
_stack_members_total ⚠.

MR (devices/mr/*): meraki_mr_clients_connected ✔; _connection_stats_total ⚠ (30-min window);
_radio_broadcasting/_channel/_channel_width_mhz/_power_dbm (channel is a VALUE not label ✔);
_cpu_load_5min; power/port info gauges (info-pattern ✔) but _port_link_negotiation_speed_mbps /
_aggregation_speed_mbps ⚠ mbps; packet families meraki_mr_packets_* / _packet_loss_*_percent ⚠
(windowed _total + _percent); network-level twins same ⚠; meraki_mr_ssid_usage_*_mb/_percentage ⚠
(+ssid only — bounded ✔).

MX: _uplink_info ✔; _uplink_loss_percent ⚠; _uplink_latency_ms ⚠; _uplink_{sent,recv}_bytes ✔;
_vpn_peer_status/_vpn_peers_total ⚠; _vpn_usage_{sent,recv}_kb ⚠; _vpn_stats_avg_latency_ms ⚠;
_firewall_rules_total ⚠ /_firewall_default_policy; _security_events_count (✔ F-091);
_performance_score; _ha_* ✔.

MG: _uplink_status_info ✔, _uplink_signal_rsrp_dbm ✔, _signal_rsrq_db ✔, _roaming ✔.
MV: _people_count, _analytics_zones, retention/audio booleans, _quality_retention_info ✔.

MT sensor (FAST): _temperature_celsius ✔, _humidity_percent, _co2_ppm, _tvoc_ppb, _pm25_ug_m3,
_no2_ppb, _o3_ppb, _pm10_ug_m3, _noise_db, _indoor_air_quality_score, _door_status,
_water_detected, _battery_percentage ⚠(-age), _voltage_volts, _current_amps, _real_power_watts,
_apparent_power_va, _power_factor_percent, _frequency_hz, _downstream_power_enabled,
_remote_lockout_status, _gateway_rssi, _gateway_last_connected_timestamp_seconds ✔.
MT alerts: meraki_mt_alerting_sensors_count (✔ _count).

NETWORK HEALTH: meraki_ap_channel_utilization_{2_4,5}ghz_percent + network twins (+utilization_type);
meraki_network_wireless_connection_stats_total ⚠ (30-min window);
meraki_network_wireless_download_kbps/_upload_kbps — ⚠⚠ DOUBLE BUG: name says kbps (reads
kilobits/s) but VALUE is kiloBYTES/s (F-065) → rename to _bytes_per_second + scale;
meraki_network_bluetooth_clients_total ⚠; meraki_mr_ssid_failed_connections_total ⚠ (windowed);
meraki_mr_device_latency_ms / _network_client_latency_ms ⚠; air-marshal
{ssids,bssids,contained_bssids,wired_detected}_total (bounded counts).

ALERTS: meraki_alerts_active ✔(+severity/type), _alerts_total_by_severity/_by_network ⚠,
meraki_sensor_alerts_total ⚠, meraki_network_health_alerts_total ⚠.

CLIENTS (opt-in): client_status, _client_usage_{sent,recv,total}_kb ⚠,
_client_application_usage_*_kb ⚠, wireless_client_rssi/_snr, _capabilities_count,
_clients_per_ssid_count, _clients_per_vlan_count — ALL carry [org][net]+client_id+mac+
description+hostname(+ssid) ⚠⚠ → #533 contract change (ID-only + meraki_client_info join).

SELF-METRICS: comprehensive and mostly correct (durations H, counts C ending _total,
staleness via success_timestamp). Exceptions → #532: `meraki_exporter_cardinality_analyzed_total`
is a GAUGE (cardinality.py:117); `meraki_exporter_collection_errors_total_expired` is a
COUNTER not ending in _total (metric_expiration.py:91); `meraki_exporter_cache_size_tracked_metrics`
misnamed string-concat (metric_expiration.py:96). Gaps → #537: no build_info; no org-budget
headroom gauge.

## Findings → issues

- MET-01 (P1) `_total` on gauge snapshot counts → #531. NOTE: F-091 consciously KEPT these
  — that decision is now superseded by Rob's rename-now call.
- MET-02 (P1) `_total` on WINDOWED/resetting gauges (most dangerous class) → #531.
- MET-03 (P1) `_count` vs `_total` inconsistency for identical semantics → #531.
- MET-04 (P1) non-base units (_kb/_mb/_kbps/_ms/_minutes/_days/_watthours) → #531; verify
  each source field's true unit against the spec before scaling; APIDEV-03's ×1024-vs-×1000
  standardization folds in here.
- MET-05 (P1) _percent (10 names) vs _percentage (3: org_application_usage, mr_ssid_usage,
  mt_battery) → #531.
- MET-06 (P1) self-metric typing → #532.
- MET-07 (P2) client PII labels → #533 (decided: ID-only + info join).
- MET-08 (P2) mutable name labels on every series (churn/orphans on rename; inventory.py:143
  already applies the ids-only pattern to filter gauges) → #534.
- MET-09 (P2) ~12 windowed metrics whose HELP omits the window → #536. Verified list:
  wireless_client_rssi/_snr (5-min avg); capabilities/per-ssid/per-vlan counts (1h);
  device_memory_used/free (5-min interval, +stat label); mx_vpn_stats_avg_latency_ms (5-min);
  ap/network channel-utilization (10-min bucket); download/upload kbps (5-min bucket);
  mr_device/_network_client latency (1h); air-marshal bssids/contained/wired (1h);
  minor: mx_vpn_usage_*_kb, mx_security_events_count, cardinality_duration_seconds.
- MET-10 (P2) build_info + budget headroom → #537. MET-11 (P3) dead enums → #538
  (7 from MET lane: ORG_LOGIN_SECURITY_ENABLED, ORG_LOGIN_SECURITY_IP_RESTRICTIONS_ENABLED,
  NETWORK_CLIENTS_TOTAL, NETWORK_DEVICE_STATUS, NETWORK_TRAFFIC_BYTES, HEALTH_ALERT_INFO,
  ORGANIZATION_HEALTH_ALERTS_TOTAL; DOC lane counted 8 — reconcile by grep at fix time).
- MET-12 (P3) duplicate webhook counters + org-vs-exporter api_requests_total collision → #539.

## Cardinality at LARGE scale (5 orgs / 500 nets / 5k devices, MR-heavy)

- MS ports = #1 driver: ~34 per-port families; a 48-port switch ≈ 1,600 series; 200
  switches ≈ 320k series. Bounded values — volume, not explosion.
- MR radio + packet-loss = #2: ~4k APs × (4 radio × 2-3 bands + 9 loss families) ≈ 108k.
- device up/status/memory ≈ 30k. Org/network/config small.
- Realistic total clients-off: **~0.5–1M series** (hence #540 cardinality-cap redesign and
  #542 sizing corrections). No unbounded-VALUE label bombs in the default config: ssid
  bounded (~15/org), air-marshal aggregated, radio channel is a value. Watch items: MS
  port volume; clients-if-enabled (#533).

## Checked and found OK (do not re-flag)

- All `_info` metrics follow the info pattern (value 1 + metadata labels).
- All true Counters correctly end _total (except the two in #532).
- Durations are Histograms; counts are Counters — self-metric types otherwise right.
- MS_PORT_ERROR_ACTIVE/_WARNING_ACTIVE, MX_SECURITY_EVENTS_COUNT, MT_ALERTING_SENSORS_COUNT
  correctly avoid `_total` (F-091) — the issue is the rest weren't swept.
- SSID usage at org+ssid only; air-marshal aggregated; channel-as-value; timestamp metric
  `_seconds` + epoch; bytes families genuinely bytes; domain units (_celsius, _volts,
  _amps, _watts, _va, _hz, _dbm, _db, _ppm, _ppb, _ug_m3, score) fine — no SI base exists.
- Metrics reference docs generated with zero drift (regen + diff verified).
