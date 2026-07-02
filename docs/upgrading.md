---
title: Upgrading
description: How to upgrade the Meraki Dashboard Exporter, the breaking changes to expect at 1.0, and where breaking metric and configuration changes are announced.
tags:
  - upgrade
  - migration
  - versioning
  - metrics
---

# Upgrading

This page explains how to upgrade the exporter safely and what to check before and after each
upgrade. It also documents the deliberate, one-time breaking changes made immediately before
**1.0**, so dashboards and alerts built against pre-1.0 metric names can be migrated cleanly.

If you only read one thing: the 1.0 release includes a **single, deliberate breaking sweep** of
metric names and labels. After 1.0, Stable metrics only change through the dual-publish
deprecation window in the [Metric Stability & Deprecation Policy](stability.md).

## How to upgrade

The exporter ships as a Docker image and a Helm chart, both published per release (see the
[Release Process](development/release-process.md)). Upgrading is a matter of moving to the new
image tag.

1. **Read the [Changelog](changelog.md) first.** Every release's breaking changes, renames, and
   deprecations are listed there. Do this before bumping the tag - it is where breaking metric
   and configuration changes are announced (see [Where breaking changes are
   announced](#where-breaking-changes-are-announced)).
2. **Pin to a specific version tag**, not `:main` (which is a rolling edge build). Use the
   `vX.Y.Z` release tag for reproducible upgrades.
3. **Roll out to a non-production instance first** if you run one, scrape it, and confirm your
   dashboards and alert rules still resolve against the new metric surface.
4. **Apply the new tag to production.** The exporter is stateless (all state is derived from the
   Meraki API on each collection cycle), so a rolling restart is safe - there is no migration
   step or persistent store to convert.

!!! tip "Verify image signatures"
    Release images and charts are signed. See [Security](security.md) for how to verify
    signatures before deploying.

## Breaking changes at 1.0

The 1.0 release carries a **one-time, pre-1.0 breaking sweep**. This churn is explicitly
permitted by, and described in, the [Metric Stability & Deprecation
Policy](stability.md#one-time-pre-1-0-sweep) - it happens exactly once so that the disruptive
renames land before the compatibility promise takes effect, rather than trickling out afterwards.

### Metric name and unit renames

Metric names were corrected so that suffixes and units are consistent and base-SI:

- `_total` suffixes now denote **only** true monotonic counters. Windowed and snapshot gauges
  that previously carried `_total` were renamed to `_count` or bare-plural forms, with any
  measurement window documented in the metric's `# HELP`.
- Non-base units were converted to base-SI (`bytes`, `seconds`, `joules`). The only retained
  non-base units are the documented exceptions that carry their unit in the name: device memory
  in KiB (binary `×1024`), link speed as `_mbps`, and the radio-native `_mhz` / `_dbm` units.
- `_percent` and other unit suffixes were standardised.

The authoritative, per-metric list of current names, labels, and units is the generated
[Complete Metrics Reference](metrics/metrics.md). Diff your dashboard and alert queries against
it after upgrading.

### Mutable name labels moved to `_info` join metrics

Mutable, human-readable **name** labels - `org_name`, `network_name`, device `name`,
`port_name`, `description`, `hostname`, and similar - were **dropped from numeric metric
series** and moved onto id-keyed `*_info` join metrics. Per-client series were reduced to
ID-only.

This was done because a rename (of an org, network, or port) would otherwise change the label
set of every affected series, starting a *new* Prometheus time series and orphaning the old one -
breaking `rate()` / `increase()` continuity. Keying numeric series by the stable **ID** and
carrying the mutable name on a separate `_info` metric means a rename touches exactly one info
series instead of the whole fleet.

**What you must change:** any query or dashboard panel that selected or displayed a name label
directly off a numeric series. Join to the info metric on the ID to pull the name back in:

```promql
meraki_device_up
  * on (serial) group_left (name)
  meraki_device_status_info
```

The same pattern applies to organizations (`on (org_id) group_left (org_name) meraki_org_info`)
and to clients (join to `meraki_client_info`). The info carriers are `meraki_org_info`,
`meraki_device_status_info`, `meraki_network_info`, `meraki_ms_port_info`, `meraki_mv_zone_info`,
and `meraki_client_info`. Full detail is in the stability policy's [Name labels are not part of
numeric series](stability.md#name-labels-are-not-part-of-numeric-series) section.

### Single-org deployment contract

From 1.0, the recommended and supported deployment model is **one exporter instance per Meraki
organization**: set `MERAKI_EXPORTER_MERAKI__ORG_ID` to the organization you want that instance
to poll. Running one instance per org keeps each poller's rate-limit budget, inventory cache, and
metric cardinality scoped to a single organization.

`MERAKI_EXPORTER_MERAKI__ORG_ID` remains optional in configuration - if it is unset the exporter
discovers and polls every organization the API key can see - but for production deployments,
prefer pinning one org per instance. See the [Configuration](config.md) reference for the key and
the [Scaling Guide](scaling-guide.md) for per-scale deployment recommendations.

## Where breaking changes are announced

Breaking metric and configuration changes are announced in the [Changelog](changelog.md), which
is generated from Conventional Commits by release-please (see the [Release
Process](development/release-process.md)).

The conventions the project follows so you can spot them:

- **Breaking changes** are flagged with a `!` in the commit type (e.g. `feat(metrics)!: ...`) or
  a `BREAKING CHANGE:` footer. These surface as a dedicated breaking-changes section in the
  changelog for that release and drive the semantic-version bump.
- **Metric deprecations and removals** are called out in the changelog and follow the
  dual-publish deprecation window described in the [Metric Stability & Deprecation
  Policy](stability.md#post-1-0-rename-deprecation-process): a Stable metric is emitted under both
  the old and new name for at least one full minor release before the old name is removed, and the
  old metric's `# HELP` is prefixed with a `DEPRECATED:` note naming the replacement.

Always read the changelog entry for the version you are moving to before upgrading production.
