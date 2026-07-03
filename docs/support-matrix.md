---
title: Support Matrix
description: Per-product-line collection coverage, tested hardware, and explicit non-goals
---

# Support Matrix

This page states, per Meraki product line, what the exporter actually collects today — as
opposed to what is aspirational or merely planned. "Supported" means the collector is enabled by
default and has been exercised against real hardware in the maintainer's homelab. "Best-effort"
means the collector exists, is shipped, and follows the published Meraki API/OpenAPI spec, but has
not been verified against live hardware of that type. "Not collected" means there is currently no
collector for that data at all.

!!! note "Source of truth"
    This matrix is derived directly from the collectors present in
    `src/meraki_dashboard_exporter/collectors/devices/` and the metric enums in
    `core/constants/metrics_constants.py` — not from aspiration. If you find a mismatch between
    this page and actual behavior, please [open an issue](https://github.com/rknightion/meraki-dashboard-exporter/issues).

## Tested hardware

The maintainer's homelab currently has:

- **MR** (wireless access points)
- **MS** (switches)
- **MT** (environmental sensors)

These three product lines are exercised against live hardware on an ongoing basis and are
considered fully **supported**.

**MX** (security appliances), **MG** (cellular gateways), and **MV** (security cameras) are not
present in the homelab. Their collectors are implemented against the published Meraki OpenAPI spec
and SDK, and are shipped and enabled, but are **best-effort**: they have not been confirmed against
real hardware of those types. See [`README.md`](https://github.com/rknightion/meraki-dashboard-exporter#readme)
for the standing disclaimer. If you run MX/MG/MV hardware and hit a bug or a missing field, please
open an issue — reports from real deployments are how these move from best-effort to supported.

## Per-product-line coverage

| Product line | Status | Collector | Notes |
|---|---|---|---|
| **MR** (wireless) | Supported | `collectors/devices/mr/` (`wireless.py`, `clients.py`, `client_logs.py`, `performance.py`, `rf_profiles.py`, `signal_quality.py`, `catalyst.py`, `firewall.py`) | Broadest coverage of any product line — ~45 dedicated metrics (`MRMetricName`) covering radio/SSID performance, per-AP signal quality (opt-in fan-out, see below), RF profiles, and client counts. Tested continuously against live APs. |
| **MS** (switches) | Supported | `collectors/devices/ms.py`, `ms_power.py`, `ms_stack.py` | ~44 dedicated metrics (`MSMetricName`) covering port status/traffic/errors, PoE power draw, and switch-stack topology. Tested continuously against live switches. |
| **MT** (sensors) | Supported | `collectors/devices/mt.py` | ~27 dedicated metrics (`MTMetricName`) covering all published sensor data fields (temperature, humidity, water detection, door, CO2, noise, PM2.5, indoor air quality, etc.) plus sensor-gateway (Bluetooth) connection status. Tested continuously against live MT sensors — this is the maintainer's most heavily-verified product line. |
| **MX** (security appliances) | Best-effort | `collectors/devices/mx.py`, `mx_firewall.py`, `mx_ha.py`, `mx_uplink_health.py`, `mx_uplink_usage.py`, `mx_vpn.py` | ~36 dedicated metrics (`MXMetricName`) covering uplink health/usage, HA/warm-spare status, site-to-site VPN status, and firewall rule counts. Implemented and enabled by default, but not verified against live MX hardware — see the hardware caveat above. |
| **MG** (cellular gateways) | Best-effort | `collectors/devices/mg.py` | ~11 dedicated metrics (`MGMetricName`) covering cellular uplink status, signal quality, and band configuration. No usage-history endpoint is collected (Meraki does not expose one comparable to MX/MR uplink usage). Not verified against live MG hardware. |
| **MV** (security cameras) | Best-effort | `collectors/devices/mv.py` | ~10 dedicated metrics (`MVMetricName`) covering camera quality/retention settings and Sense (analytics) configuration. This is the thinnest of the six device collectors — MV analytics/telemetry coverage is minimal compared to MR/MS/MT. Not verified against live MV hardware. |

Beyond the six device-specific collectors, `DeviceMetricName` (~7 metrics) and
`NetworkMetricName`/`NetworkHealthMetricName` (device-agnostic health signals such as connection
stats, bluetooth, data rates) apply across all product lines uniformly, and `OrgMetricName`
(~46 metrics), `ClientMetricName`, and `AlertMetricName` cover organization-wide, client-level, and
alerts data that is not tied to a single product line.

### Optional / opt-in collection

A few things are shipped but **off by default** and must be explicitly enabled:

- **Per-AP signal quality** (`collectors.collect_ap_signal_quality`, default **on**, but costs one
  API call per selected AP per cycle — scope it with `collectors.ap_signal_quality_tags` or
  disable it for large MR fleets).
- **Meraki Insight** (`collectors.collect_insight`, default **off**) — see below.

## Non-goals

### Meraki Insight — opt-in, license-gated, best-effort

Meraki Insight (WAN/application-health analytics layered on MX appliances) **is collected**, but
only when explicitly turned on:

- Config key: `collectors.collect_insight` (env `MERAKI_EXPORTER_COLLECTORS__COLLECT_INSIGHT`),
  default **`false`**.
- When enabled, a second flag `collectors.insight_app_health_enabled`
  (env `MERAKI_EXPORTER_COLLECTORS__INSIGHT_APP_HEALTH_ENABLED`), default **`true`**, additionally
  fans out per-network × per-monitored-application health metrics.
- ~9 dedicated metrics (`InsightMetricName`) cover monitored-application counts and per-application
  latency/loss/response-duration/throughput/client-count.
- **License-gated**: Insight requires a separate Meraki license on the organization. A
  non-Insight org returns an error for the Insight endpoints, which the collector treats as "not
  available" and skips at debug level rather than failing.
- **Best-effort / spec-only pre-launch**: the maintainer's homelab has neither an Insight license
  nor an MX appliance, so this entire family has not been exercised against a live Insight-enabled
  organization. Two fields (`wanGoodput`/`lanGoodput`) are deliberately not emitted at all because
  the spec gives no unit for them.

If you run Meraki Insight and can help verify the live response shapes, please open an issue.

### Meraki Systems Manager — explicit non-goal

**Meraki Systems Manager (SM)**, Meraki's MDM/endpoint-management product, is **not collected at
all** and there is no SM collector in this codebase. This is a deliberate non-goal for this
exporter, not an oversight or a gap awaiting implementation. There is no config flag to enable it
because no code path exists.

## Supported regions

The exporter talks to whichever Meraki API base URL it is configured with
(`meraki.api_base_url`, env `MERAKI_EXPORTER_MERAKI__API_BASE_URL`). The following regional base
URLs are recognized out of the box:

| Region | Base URL |
|---|---|
| Global / default | `https://api.meraki.com/api/v1` |
| Canada | `https://api.meraki.ca/api/v1` |
| China | `https://api.meraki.cn/api/v1` |
| India | `https://api.meraki.in/api/v1` |
| US Federal (GovCloud) | `https://api.gov-meraki.com/api/v1` |

A well-formed `http(s)` URL that is *not* one of the values above (e.g. a custom proxy, or a future
Meraki region not yet in this list) is still accepted — the exporter logs a warning but does not
reject it, so custom endpoints and not-yet-catalogued regions keep working.

All testing has been performed against the global/default region; the regional endpoints above are
supported on the assumption that they implement the same OpenAPI-documented API surface as the
default region (Meraki publishes the same spec for all regions), not because each has been
individually exercised.
