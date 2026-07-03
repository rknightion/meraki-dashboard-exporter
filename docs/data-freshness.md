---
title: Data Freshness & Alerting Guidance
description: How stale each metric can be, Meraki-side detection lag, and recommended alert `for:` durations
---

# Data Freshness & Alerting Guidance

The exporter is a **polling** exporter: every collector runs on a fixed schedule (an "update
tier") and Prometheus scrapes whatever the last completed cycle produced. On top of that,
inbound [webhooks](getting-started.md) can *accelerate* one specific signal — whole-device
down detection — ahead of the next poll. Understanding both halves is required to pick correct
`for:` durations on your alert rules; getting this wrong is the single most common cause of
alerts that either never fire or fire on transient blips.

!!! warning "Webhooks are down-only, not real-time"
    Despite older marketing language, webhooks do **not** make the exporter real-time. They only
    fast-flip `meraki_device_up` to `0` on a whole-device-down event, ahead of schedule. Device
    **recovery** (`meraki_device_up` back to `1`) and every other metric in the exporter remain
    fully poll-paced — there is no whole-device "back online" webhook alert type to drive a fast
    recovery path. See [Webhook-driven fast path](#webhook-driven-fast-path-device-down-only)
    below.

## Update tiers

Every collector is registered against exactly one tier (`core/constants/device_constants.py::UpdateTier`),
and each tier has a configurable interval (`MERAKI_EXPORTER_UPDATE_INTERVALS__*`, see
[Configuration](config.md)):

| Tier | Default interval | Configurable range | Env var |
| --- | --- | --- | --- |
| FAST | 60s | 30–300s | `MERAKI_EXPORTER_UPDATE_INTERVALS__FAST` |
| MEDIUM | 300s | 300–1800s | `MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM` |
| SLOW | 900s | 600–3600s | `MERAKI_EXPORTER_UPDATE_INTERVALS__SLOW` |

Every collector also has an independent per-run timeout budget
(`MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT`, default 240s) — a slow API response can push a
single cycle's effective staleness past the nominal interval; the next scheduled run still starts
on time, it just skips whatever the timed-out cycle didn't finish.

### What runs on each tier

| Tier | Collector | Data |
| --- | --- | --- |
| FAST (60s) | `MTSensorCollector` | Latest MT environmental sensor readings (temperature, humidity, CO2, water detection, etc.) and sensor-to-gateway connection status |
| MEDIUM (300s) | `DeviceCollector` | Per-device inventory metrics, including `meraki_device_up` / `meraki_device_status_info`, memory, CPU, uptime, and per-device-type detail (ports, radios, PSU, etc.) |
| MEDIUM (300s) | `NetworkHealthCollector` | Bluetooth clients, wireless connection stats, data rates, RF health, SSID performance |
| MEDIUM (300s) | `OrganizationCollector` | Org-level metrics: API usage, licensing, client overview, and related org aggregates |
| MEDIUM (300s) | `AlertsCollector` | Active Meraki Dashboard assurance alerts |
| MEDIUM (300s) | `ClientsCollector` | Optional client-inventory ID-only metrics (`collectors.clients_enabled`, off by default) |
| MEDIUM (300s) | `MTSensorAlertsCollector` | MT sensor threshold alerts |
| SLOW (900s) | `ConfigCollector` | Configuration/security data (SNMP, org security posture, etc.) |
| SLOW (900s) | `InsightCollector` | Optional Meraki Insight WAN/application health (license-gated, off by default); one internal endpoint group additionally stretches its own floor to 3600s for the monitored-application list |

Some collectors further stretch an individual endpoint group's effective cadence beyond its
registered tier via a `floor_seconds` value (see the collectors' own `CLAUDE.md` files) — the
table above reflects each collector's baseline registered tier, which is the worst case you
should assume unless you have verified a specific group's floor.

## Meraki-side detection lag

Tier cadence is only half the story. Before the exporter's MEDIUM poll can even observe a device
transitioning to offline, Cisco Meraki's own cloud has to notice the device stopped checking in
and flip its dashboard status. Cisco does not publish an exact, universal heartbeat/threshold
figure in its documentation for this.

!!! warning "⚠ Unverified figure — flagged for #619"
    We could not confirm a precise, documented number for Meraki's own offline-detection delay.
    Commonly observed behavior (community reports and casual Meraki documentation references,
    **not** an authoritative published SLA) puts this in the **low single-digit minutes** range
    for the dashboard status icon to flip, with some connectivity alert types (e.g. Auto VPN)
    explicitly documented with their own multi-minute thresholds (Cisco's own example: a Auto VPN
    down alert requires the tunnel down for "more than 5 minutes" before firing). Treat any
    specific number here as an **approximate range of a few minutes**, not a guarantee, until
    Phase 6 live verification confirms it against a real deployment.

## Worst-case device-down visibility

Combine the two lags to get the worst case a Prometheus alert should tolerate before firing:

- **Webhook-fast-path device-down** (webhooks enabled, see below): Meraki-side detection lag
  (approximate, a few minutes) + webhook delivery/processing (sub-second) ≈ **Meraki's own
  detection lag**, essentially removing the MEDIUM poll wait for the down transition.
- **Poll-path device-down** (webhooks disabled, or the down alert type isn't configured to fire
  webhooks): Meraki-side detection lag (approximate, a few minutes) + up to one full MEDIUM
  interval (default 300s) before the next poll observes it ≈ **up to ~10 minutes** worst case
  with default settings.
- **Device recovery / UP, always** (webhooks make no difference here — see below): Meraki-side
  recovery detection + up to one full MEDIUM interval ≈ the same **up to ~10 minutes** worst case,
  regardless of webhook configuration.

## Webhook-driven fast path (device-down only)

As of the webhook device-state fast path (`core/webhook_handler.py`), an inbound webhook whose
`alertType` is `device_down` or `gateway_down` (`DEVICE_DOWN_ALERT_TYPES`) flips
`meraki_device_up=0` for that device's serial immediately, ahead of the next MEDIUM poll — but
**only** for devices the exporter already knows about from a prior poll (unknown serials are a
no-op) and **only** for those two alert types (per-port/uplink/cellular/PSU/tunnel/role-change
alert types are deliberately excluded — they aren't whole-device availability signals).

There is currently **no** whole-device "back online" webhook alert type
(`DEVICE_UP_ALERT_TYPES` is intentionally empty) — Meraki's webhook alert catalog has no verified
whole-device-recovery type. Recovery is therefore reconciliation-only: the next MEDIUM poll
restores `meraki_device_up=1` once the device is actually reachable again, bounded by the same
MEDIUM-tier staleness as everything else. If Meraki later documents a verified recovery alert
type, wiring it up is a one-line addition to `DEVICE_UP_ALERT_TYPES`.

Webhooks are opt-in and off by default (`MERAKI_EXPORTER_WEBHOOKS__ENABLED=false`) — see
[Getting Started](getting-started.md) for setup. Without them enabled, device-down detection is
poll-path only, as described above.

## Recommended alert `for:` durations

The recommended `for:` durations below are the source-of-truth durations the starter alert-rule
examples should use. They're derived directly from the tier intervals above (default settings) plus
headroom for one missed scrape/eval cycle, so a transient blip in a single collection cycle doesn't
page anyone.

| Signal | Tier | Recommended `for:` | Why |
| --- | --- | --- | --- |
| MT sensor threshold breach (e.g. temperature, water) | FAST (60s) | `2m`–`3m` | Tolerates one missed FAST cycle before firing |
| `meraki_device_up == 0`, webhooks **enabled** | Fast-path (down only) + MEDIUM (poll fallback) | `3m`–`5m` | Covers Meraki-side detection lag on the fast path; falls back to the poll-path number below if the webhook never arrives |
| `meraki_device_up == 0`, webhooks **disabled** (or for recovery/UP in all cases) | MEDIUM (300s) | `12m`–`15m` | One full MEDIUM interval + Meraki-side detection lag + headroom for a missed cycle |
| Network health / RF / connection-stats thresholds | MEDIUM (300s) | `10m`–`15m` | Same MEDIUM-tier reasoning; these have no webhook fast path at all |
| Organization-level (licensing, API usage) | MEDIUM (300s) | `15m` | Slow-changing aggregates; false-positive avoidance favored over speed |
| Configuration/security posture drift | SLOW (900s) | `20m`–`30m` | Slow-changing by nature; avoid paging on a single SLOW cycle hiccup |

Keep these durations in sync with the starter alert-rule examples (tracked separately) so the two
documents never drift apart.

## See also

- [Getting Started](getting-started.md) — webhook setup instructions
- [Configuration](config.md) — full list of update-interval and collector-timeout environment variables
- [Security](security.md) — webhook shared-secret and endpoint authentication
