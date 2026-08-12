---
title: Support Matrix
description: Per-product-line collection coverage, tested hardware, and explicit non-goals
---

# Support Matrix

This page states the evidence level behind each product family, rather than treating shipped code
as live support. **Live-verified** means the named response envelope was observed on maintainer
hardware; **spec-verified** means code was checked against the Meraki OpenAPI specification, SDK,
and vendor documentation; **community-reported** is reserved for a sanitised real response supplied
by a user and recorded in the fixture corpus. It is not a promise that every endpoint, scale, or
pagination shape was observed.

!!! note "Source of truth"
    This matrix is derived directly from the collectors present in
    `src/meraki_dashboard_exporter/collectors/devices/` and the metric enums in
    `core/constants/metrics_constants.py` — not from aspiration. If you find a mismatch between
    this page and actual behavior, please [open an issue](https://github.com/rknightion/meraki-dashboard-exporter/issues).

## Verification scope

The maintainer's homelab currently has:

- **MR** (wireless access points)
- **MS** (switches)
- **MT** (environmental sensors)

The live scope is **one network only**. It does not verify multi-site discovery, NetworkFilter
behavior across sites, pagination, or large-fleet fan-out. The date and scope in the table are the
current evidence record as of **2026-08-12**.

**MX**, **MG**, and **MV** are not present in the homelab. A sanitised response from a real
deployment can move a response envelope from spec-verified to community-reported; maintainers then
add it through the corpus and preset path tracked in #713.

## Per-product-line coverage

| Product family | Verification level (date and checked scope) | Collector | Coverage and limits |
|---|---|---|---|
| **MR** (wireless) | **Live-verified — 2026-08-12:** one MR56 response envelope. Multi-AP scale, pagination, SSID counts, and packet-loss shapes remain unverified. | `collectors/devices/mr/` | ~45 dedicated metrics for radio/SSID performance, opt-in per-AP signal quality, RF profiles, and client counts. |
| **MS** (pre-Catalyst switches) | **Live-verified — 2026-08-12:** MS120-8LP and MS250-24P envelopes. 500+ switches, stacks, and page boundaries remain unverified. | `collectors/devices/ms.py`, `ms_power.py`, `ms_stack.py` | ~44 dedicated port, PoE, and stack metrics. |
| **MT** (sensors) | **Live-verified — 2026-08-12:** 16 sensor-reading envelopes. Not every reading variant, gateway link, or multi-network page was observed. | `collectors/devices/mt.py` | ~27 sensor and sensor-gateway metrics. |
| **Catalyst / CS switches** | **Spec-verified — 2026-08-12:** routing through MS. No live device, stack, or port response observed. | MS routing | Uses the MS collector; no distinct live evidence. |
| **Catalyst CW APs** | **Spec-verified — 2026-08-12:** routing through MR. No controller-association response observed. | MR routing | Uses the MR collector; no distinct live evidence. |
| **MX** (security appliances) | **Spec-verified — 2026-08-12:** SDK, vendor docs, and spec only. No live MX, HA, VPN, uplink, firewall, or security-event sample. | `mx.py`, `mx_firewall.py`, `mx_ha.py`, `mx_uplink_health.py`, `mx_uplink_usage.py`, `mx_vpn.py` | ~36 dedicated metrics. |
| **Z-series / vMX** | **Spec-verified — 2026-08-12:** code and spec through MX routing only. | MX routing | No separate live response evidence. |
| **MG** (cellular gateways) | **Spec-verified — 2026-08-12:** SDK and spec only. No uplink, eSIM, tower, or HA sample. | `collectors/devices/mg.py` | ~11 dedicated metrics. |
| **MV** (security cameras) | **Spec-verified — 2026-08-12:** SDK and spec only; deprecations are tracked in #691. | `collectors/devices/mv.py` | ~10 quality, retention, and Sense-configuration metrics. |

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
