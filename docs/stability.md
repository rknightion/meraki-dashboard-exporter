---
title: Metric Stability & Deprecation Policy
description: The 1.0 compatibility promise for Meraki Dashboard Exporter metric names, labels, and units - what is stable, what is experimental, and how post-1.0 renames are handled.
tags:
  - prometheus
  - metrics
  - stability
  - versioning
---

# Metric Stability & Deprecation Policy

This page is the **compatibility contract** for the metrics this exporter exposes on
`/metrics`. It states which metrics you can safely build dashboards and alerts against, what
the 1.0 release promises (and deliberately does *not* promise), and how metric names, labels,
and units will change after 1.0.

If you only read one thing: **Stable metrics keep their names, labels, and base units across
1.x. Experimental metrics may change at any time.** Everything else below is detail.

!!! abstract "Scope"
    This contract covers the Prometheus metrics on the `/metrics` endpoint only. It does not
    cover the OpenTelemetry **tracing** output (spans are not a stable API), the HTML `/status`
    and `/cardinality` pages, the `/api/metrics/cardinality` JSON shape, log formats, or
    configuration environment variables (config compatibility is covered separately in the
    [Configuration](config.md) reference).

## Stability tiers

Every metric family belongs to one of two tiers. A "family" is the group of metrics sharing a
name prefix (e.g. `meraki_ms_*`). The authoritative, per-metric list lives in the generated
[Complete Metrics Reference](metrics/metrics.md); this page assigns each family a tier.

### Stable

Stable families are covered by the 1.0 compatibility promise below. They are exercised against
live hardware (MT, MR, MS) or are hardware-independent infrastructure/organization metrics with
a settled contract.

| Family prefix | What it covers |
|---|---|
| `meraki_org_*` | Organization-level metrics: API request usage, device/network counts, licensing, per-org configuration and change tracking |
| `meraki_device_*` | Cross-device availability, status info, and memory |
| `meraki_ms_*` | MS switch metrics: port status/traffic/errors, power (PoE), STP, stacking |
| `meraki_mr_*` | MR wireless AP metrics: client counts, radio/channel state, CPU, packet and SSID usage |
| `meraki_mt_*` | MT sensor readings: temperature, humidity, air quality, power, water/door, battery |
| `meraki_network_*`, `meraki_ap_*`, `meraki_wireless_*` | Network-health metrics: RF/channel utilization, connection stats, Bluetooth, data rates |
| `meraki_alerts_*`, `meraki_sensor_alerts_*`, `meraki_network_health_alerts_*` | Active alert counts by severity/type/network |
| `meraki_network_filter_*` | Live network-filter scope observability |
| `meraki_webhook_*` | Webhook receiver counters and processing duration (present only when the receiver is enabled, but the contract for these names is stable) |
| `meraki_exporter_*` | Exporter self-observability: collector durations/errors, API client latency/counters, inventory cache, cardinality, metric expiration, `build_info` |
| `meraki_client_*`, `meraki_clients_*` | Per-client metrics. Stable contract: the ID-only numeric series plus the `meraki_client_info` join shape (per #533; see [Name labels](#name-labels-are-not-part-of-numeric-series)) is stable across 1.x. These are opt-in and disabled by default (`MERAKI_EXPORTER_CLIENTS__ENABLED`), so whether the series are *present* is gated by config - that non-guarantee is the "Presence of optional subsystems" bullet under [What 1.0 does NOT promise](#what-10-does-not-promise), not an exception to the name/label/unit contract. |

### Experimental

Experimental families are **explicitly excluded** from the 1.0 promise. Their names, labels,
units, and existence may change in any release, minor or patch, without a deprecation window.
Build production alerts against them at your own risk.

| Family prefix | Why it is experimental |
|---|---|
| `meraki_mx_*` | MX security-appliance metrics (uplink health/usage, VPN, firewall, HA, performance). No live MX hardware is available to the maintainer; these are best-effort, driven from public API/SDK docs (see the note in the project README) and not verified against real devices. |
| `meraki_mg_*` | MG cellular-gateway metrics. Same best-effort, no-live-hardware caveat as MX. |
| `meraki_mv_*` | MV camera metrics (people counting, analytics zones, retention/audio). Same best-effort caveat, and the underlying analytics surface is subject to change. |

!!! tip "Which tier is a metric in?"
    Match the metric's name prefix to the tables above. If a metric's family is not listed
    (for example a brand-new family added after this page was last updated), treat it as
    **Experimental** until it is explicitly promoted here.

## What 1.0 promises

For **Stable** metrics, within the 1.x series the exporter promises:

- **Names are stable.** A Stable metric will not be renamed within 1.x except through the
  deprecation process below (dual-publish, then removal in a later minor).
- **Labels are stable and additive.** Existing label *keys* on a Stable metric will not be
  removed or repurposed. New label keys may be *added* (see [Labels are
  additive](#labels-are-additive)).
- **Units are base-SI and stable.** Values are exposed in Prometheus base units - `bytes`,
  `seconds`, `joules`, ratios `0-1` where applicable - and the unit of a Stable metric will
  not change under a fixed name. The deliberate, documented exceptions carry their unit in the
  name and are themselves stable: device memory in KiB (binary `×1024`), link speed as
  `_mbps`, and the domain-native `_mhz` / `_dbm` radio units. Base-unit conventions and the
  `_count` / bare-plural / `_total` suffix meanings are defined in the
  [Metrics Overview](metrics/overview.md).
- **Metric type is stable.** A gauge stays a gauge, a counter stays a counter. `_total`
  suffixes denote genuine monotonic counters only.

## What 1.0 does NOT promise

Even for Stable metrics, the following are explicitly **not** part of the contract and may
change in any release:

- **HELP / description text.** The human-readable `# HELP` wording may be reworded, clarified,
  or corrected at any time. Do not parse or assert on HELP strings.
- **Exact cardinality.** The number of series a metric produces depends on your inventory
  (orgs, networks, devices, ports, SSIDs) and on cardinality-management behaviour, both of
  which may change. Do not assume a fixed series count.
- **Experimental metrics.** Everything in the Experimental tier above - names, labels, units,
  and existence.
- **Label *values*.** The set of possible values for a label (e.g. new `product_type`,
  `status`, or `model` strings) tracks the Meraki API and grows or changes as Meraki does.
- **Presence of optional subsystems.** Metrics that only appear when an opt-in feature is
  enabled (clients, webhooks) are present only under that configuration.

## Labels are additive

New labels may appear on an existing Stable metric in a future release. This is a compatible
change and is explicitly permitted by this policy:

- **The meaning of an existing label will never silently change.** If `network_id` means the
  network ID today, it will always mean the network ID.
- **New label keys may be added** to an existing metric to expose additional dimensions.

!!! warning "Write queries that tolerate new labels"
    A new label key changes a series' identity in Prometheus. Aggregating queries
    (`sum by (...)`, `sum without (...)`) already tolerate this. Exact-match selectors that
    pin *every* label do not - prefer selecting the labels you care about and letting the rest
    vary. This is standard Prometheus practice and is the consumer's responsibility under this
    contract.

## Name labels are not part of numeric series

**Decision (settled contract).** Mutable, human-readable **name** labels - `org_name`,
`network_name`, device `name`, `port_name`, `description`, `hostname`, and similar - are
**dropped from numeric metric series** and instead exposed on an id-keyed `*_info` join metric.

**Why.** A name is mutable: an operator renaming an organization, network, or port would
otherwise change the label set of every affected series. In Prometheus that starts a *new* time
series and orphans the old one, breaking `rate()` / `increase()` continuity and littering the
TSDB with dead series on every rename. Keying numeric series by the stable **ID** and carrying
the mutable name on a separate `_info` metric decouples "the measurement" from "the current
display name", so a rename touches exactly one info series instead of the whole fleet.

**How to get names back in a query.** Join the numeric series to the info metric on the ID and
pull the name across with `group_left`:

```promql
meraki_device_up
  * on (serial) group_left (name)
  meraki_device_status_info
```

The same pattern applies to organizations (`on (org_id) group_left (org_name)
meraki_org_info`) and to clients, whose numeric series are ID-only and join to
`meraki_client_info`. This mirrors the established info-join used for organization/device
identity; the network-filter observability gauges in `services/inventory.py` already follow it
(they deliberately omit `network_name` from their labels to avoid orphan series on rename).

!!! info "Rollout"
    This policy is stated here as settled contract. The code that strips mutable name labels
    from numeric series and moves them onto `_info` metrics lands as part of the pre-1.0 metric
    sweep; once complete, the [Complete Metrics Reference](metrics/metrics.md) is the source of
    truth for exactly which labels each metric carries.

## Post-1.0 rename & deprecation process

After 1.0, a Stable metric is only renamed (or has a label renamed, or a unit corrected via a
new name) through a **dual-publish deprecation window**:

1. **Add the new name.** The new metric is emitted alongside the old one. Both carry identical
   values.
2. **Mark the old name deprecated.** The old metric's `# HELP` text is prefixed with a
   `DEPRECATED:` note that names the replacement and the earliest release in which the old
   metric may be removed.
3. **Dual-publish for at least one minor release.** Both names are emitted together for a
   minimum of one full minor release (`1.n` → `1.n+1`), giving consumers time to migrate
   dashboards and alerts.
4. **Remove the old name in a later minor.** Removal happens no earlier than the release named
   in the deprecation note, and never in a patch release.

Deprecations and removals are called out in the [Changelog](changelog.md). Breaking metric
changes that cannot follow this process are reserved for a future **2.0**.

## One-time pre-1.0 sweep

The metric surface underwent a **single, deliberate, breaking rename-and-unit sweep immediately
before 1.0** to establish clean, consistent, base-unit names *before* the compatibility promise
takes effect. This sweep:

- corrected `_total` suffixes so they denote only true monotonic counters (windowed and
  snapshot gauges were renamed to `_count` / bare-plural forms, with any measurement window
  documented in HELP);
- converted non-base units to base-SI (`bytes`, `seconds`, `joules`), keeping only the
  documented exceptions (memory KiB `×1024`, link-speed `_mbps`, radio `_mhz` / `_dbm`);
- standardised `_percent` and other unit suffixes; and
- moved mutable name labels off numeric series onto `_info` join metrics (above), and reduced
  client series to ID-only.

!!! success "This churn happens once"
    This one-time sweep is **explicitly permitted by this policy** and was done *before* the
    1.0 promise applied, so that the disruptive renames happen exactly once rather than
    trickling out under the post-1.0 deprecation process. From 1.0 onward, Stable-metric names
    change only through the dual-publish deprecation window above. It did **not** use the
    dual-publish window because it predates the promise.
