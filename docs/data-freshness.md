---
title: Data Freshness & Alerting Guidance
description: How stale each metric can be, Meraki-side detection lag, and recommended alert `for:` durations
---

# Data Freshness & Alerting Guidance

The exporter is a **polling** exporter: every collector runs its own group-clocked loop and
Prometheus scrapes whatever the last completed cycle produced. On top of that, inbound
[webhooks](getting-started.md) can *accelerate* one specific signal — whole-device down
detection — ahead of the next poll. Understanding both halves is required to pick correct
`for:` durations on your alert rules; getting this wrong is the single most common cause of
alerts that either never fire or fire on transient blips.

!!! warning "Webhooks are down-only, not real-time"
    Despite older marketing language, webhooks do **not** make the exporter real-time. They only
    fast-flip `meraki_device_up` to `0` on a whole-device-down event, ahead of schedule. Device
    **recovery** (`meraki_device_up` back to `1`) and every other metric in the exporter remain
    fully poll-paced — there is no whole-device "back online" webhook alert type to drive a fast
    recovery path. See [Webhook-driven fast path](#webhook-driven-fast-path-device-down-only)
    below.

## Per-group solved intervals are the freshness source of truth

There is no fixed FAST/MEDIUM/SLOW tier system. Instead, an adaptive scheduler
(`core/scheduler.py`, see [Scheduler Architecture](observability/scheduler.md) for the full
mechanism) groups every API fetch into one of dozens of **endpoint groups**, each declared
with a `floor_seconds` — the natural volatility window below which polling it faster would
be wasted API budget (e.g. MT sensor readings floor at 60s, org licensing floors much
higher). Every group starts pinned at its own floor; the solver only **stretches** a
group's interval above its floor when the combined request demand across all groups would
exceed the configured API budget (`requests_per_second × shared_fraction`, scaled by
`scheduler.target_utilization`), and it always stretches the lowest-priority, least-stretched
group first. A given group's *effective* interval can therefore differ between two
deployments (or over time in the same deployment) depending on organization size and how
close the estate is to the configured budget — there is no longer a single global "MEDIUM =
300s" number that applies everywhere.

Each collector owns one or more endpoint groups and runs its own loop, sleeping until the
earliest-due of its groups (`EndpointScheduler.seconds_until_due`). A collector's overall
**cadence** — the number to reason about for staleness/alerting purposes — is the smallest
solved interval among its own enabled, gated groups (`MetricCollector.collector_cadence_seconds()`).

**Where to read the live numbers for your deployment:**

- The `/status` dashboard's **Endpoint Groups** table (also available as JSON via
  `/status?format=json`) lists every group's current solved interval, stretch factor, priority,
  and whether it's pinned.
- `meraki_exporter_scheduler_interval_seconds{group}` — the live solved interval for each
  endpoint group, as a Prometheus gauge.
- `meraki_exporter_collector_cadence_seconds{collector}` — the live effective cadence per
  collector (the number to compare a collector's last-success age against).

Every collector also has an independent per-run timeout budget
(`MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT`, default 240s) — a slow API response can push a
single cycle's effective staleness past the nominal interval; the next scheduled run still starts
on time, it just skips whatever the timed-out cycle didn't finish.

### Approximate cadence by collector (default settings, small-to-medium estate)

These are the **floor-derived defaults** you'll typically see when the estate is small enough
that the solver hasn't needed to stretch anything — check `/status` or the gauges above for
your actual deployment's live numbers, since a larger estate against a fixed API budget will
show longer effective intervals for lower-priority groups.

| Collector | Typical cadence | Data |
| --- | --- | --- |
| `MTSensorCollector` | ~60s | Latest MT environmental sensor readings (temperature, humidity, CO2, water detection, etc.) and sensor-to-gateway connection status |
| `DeviceCollector` | ~300s | Per-device inventory metrics, including `meraki_device_up` / `meraki_device_status_info`, memory, CPU, uptime, and per-device-type detail (ports, radios, PSU, etc.) |
| `NetworkHealthCollector` | ~300s | Bluetooth clients, wireless connection stats, data rates, RF health, SSID performance |
| `OrganizationCollector` | ~300s | Org-level metrics: API usage, licensing, client overview, and related org aggregates |
| `AlertsCollector` | ~300s | Active Meraki Dashboard assurance alerts |
| `ClientsCollector` | ~300s | Optional client-inventory ID-only metrics (`collectors.clients_enabled`, off by default) |
| `MTSensorAlertsCollector` | ~300s | MT sensor threshold alerts |
| `ConfigCollector` | ~900s | Configuration/security data (SNMP, org security posture, etc.) |
| `InsightCollector` | ~900s+ | Optional Meraki Insight WAN/application health (license-gated, off by default); its monitored-application-list group floors even higher (3600s) |

## Meraki-side detection lag

A group's solved interval is only half the story. Before the exporter's next poll can even
observe a device transitioning to offline, Cisco Meraki's own cloud has to notice the device
stopped checking in and flip its dashboard status. Cisco does not publish an exact, universal
heartbeat/threshold figure in its documentation for this.

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

Combine the two lags to get the worst case a Prometheus alert should tolerate before firing
(using `DeviceCollector`'s device-availability group cadence, ~300s by default):

- **Webhook-fast-path device-down** (webhooks enabled, see below): Meraki-side detection lag
  (approximate, a few minutes) + webhook delivery/processing (sub-second) ≈ **Meraki's own
  detection lag**, essentially removing the poll wait for the down transition.
- **Poll-path device-down** (webhooks disabled, or the down alert type isn't configured to fire
  webhooks): Meraki-side detection lag (approximate, a few minutes) + up to one full
  `DeviceCollector` cadence (default ~300s) before the next poll observes it ≈ **up to ~10
  minutes** worst case with default settings.
- **Device recovery / UP, always** (webhooks make no difference here — see below): Meraki-side
  recovery detection + up to one full `DeviceCollector` cadence ≈ the same **up to ~10 minutes**
  worst case, regardless of webhook configuration.

## Webhook-driven fast path (device-down only)

As of the webhook device-state fast path (`core/webhook_handler.py`), an inbound webhook whose
`alertType` is `device_down` or `gateway_down` (`DEVICE_DOWN_ALERT_TYPES`) flips
`meraki_device_up=0` for that device's serial immediately, ahead of the next poll — but
**only** for devices the exporter already knows about from a prior poll (unknown serials are a
no-op) and **only** for those two alert types (per-port/uplink/cellular/PSU/tunnel/role-change
alert types are deliberately excluded — they aren't whole-device availability signals).

There is currently **no** whole-device "back online" webhook alert type
(`DEVICE_UP_ALERT_TYPES` is intentionally empty) — Meraki's webhook alert catalog has no verified
whole-device-recovery type. Recovery is therefore reconciliation-only: the next poll restores
`meraki_device_up=1` once the device is actually reachable again, bounded by the same
`DeviceCollector` cadence staleness as everything else. If Meraki later documents a verified
recovery alert type, wiring it up is a one-line addition to `DEVICE_UP_ALERT_TYPES`.

Webhooks are opt-in and off by default (`MERAKI_EXPORTER_WEBHOOKS__ENABLED=false`) — see
[Getting Started](getting-started.md) for setup. Without them enabled, device-down detection is
poll-path only, as described above.

## Recommended alert `for:` durations

The recommended `for:` durations below are the source-of-truth durations the starter alert-rule
examples should use. They're derived directly from each collector's approximate cadence above
(default settings, small estate) plus headroom for one missed scrape/eval cycle, so a transient
blip in a single collection cycle doesn't page anyone. **Prefer expressing your own alert rules
in terms of `meraki_exporter_collector_success_timestamp_seconds` and
`meraki_exporter_collector_cadence_seconds` directly** (see the staleness formula below) rather
than a hard-coded duration, since it automatically tracks whatever the solver has settled on for
your deployment.

**Generic staleness rule:** `time() - meraki_exporter_collector_success_timestamp_seconds{collector="X"} > 3 * meraki_exporter_collector_cadence_seconds{collector="X"}` — this is the same 3× multiplier the exporter's own liveness probe uses internally.

| Signal | Approx. cadence | Recommended `for:` | Why |
| --- | --- | --- | --- |
| MT sensor threshold breach (e.g. temperature, water) | ~60s | `2m`–`3m` | Tolerates one missed cycle before firing |
| `meraki_device_up == 0`, webhooks **enabled** | Fast-path (down only) + ~300s poll fallback | `3m`–`5m` | Covers Meraki-side detection lag on the fast path; falls back to the poll-path number below if the webhook never arrives |
| `meraki_device_up == 0`, webhooks **disabled** (or for recovery/UP in all cases) | ~300s | `12m`–`15m` | One full `DeviceCollector` cycle + Meraki-side detection lag + headroom for a missed cycle |
| Network health / RF / connection-stats thresholds | ~300s | `10m`–`15m` | Same cadence reasoning; these have no webhook fast path at all |
| Organization-level (licensing, API usage) | ~300s | `15m` | Slow-changing aggregates; false-positive avoidance favored over speed |
| Configuration/security posture drift | ~900s | `20m`–`30m` | Slow-changing by nature; avoid paging on a single cycle hiccup |

Keep these durations in sync with the starter alert-rule examples (tracked separately) so the two
documents never drift apart.

## See also

- [Scheduler Architecture](observability/scheduler.md) — how the solver derives per-group intervals
- [Getting Started](getting-started.md) — webhook setup instructions
- [Configuration](config.md) — full list of scheduler and collector-timeout environment variables
- [Security](security.md) — webhook shared-secret and endpoint authentication
</content>
