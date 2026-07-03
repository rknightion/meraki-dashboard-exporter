---
title: Why This Exporter
description: A factual, dated comparison of this exporter's design choices against simpler community Meraki Prometheus exporters, and when to pick each.
tags:
  - comparison
  - architecture
  - decision-guide
---

# Why This Exporter

*Last reviewed: 2026-07.*

The Meraki ecosystem has several community Prometheus exporters, most of them small
single-file scripts that poll a handful of `getOrganization*`/`getNetwork*` endpoints on a
fixed interval and print gauges. Those are good choices for a small estate or a quick proof
of concept. This page states, factually and without disparaging any specific alternative,
what this exporter does differently and why, so you can decide whether the extra surface
area is worth it for your deployment.

For the full metric-by-device-model breakdown see the [Support
Matrix](support-matrix.md), and for quick operational answers see the [FAQ](faq.md). This
page is about architecture and positioning, not a feature checklist.

## Design choices specific to this exporter

**Async collection with bounded concurrency.** The Meraki Python SDK is synchronous, so
collectors run it via `asyncio.to_thread()` and fan out per-device/per-network work through
`ManagedTaskGroup`, which caps in-flight requests at `settings.api.concurrency_limit` rather
than firing an unbounded `asyncio.gather()`. This keeps a single collection cycle from
saturating the Meraki API's per-organization rate limit even against large estates.

**An adaptive, budget-aware endpoint scheduler, not one fixed interval.** Every API fetch is
declared as an endpoint group with its own volatility floor (`core/scheduler.py`) — sensor
readings floor around 60s, device/org/network-health groups around 300s, configuration and
security settings much higher — and each collector runs its own group-clocked loop off those
floors, so a dashboard's sensor panel refreshes every minute without re-fetching device
inventory every minute too. On top of the floors, the scheduler (`scheduler.mode=adaptive`,
the **default**, not an opt-in) automatically stretches individual groups' intervals when their
combined request demand would exceed the configured API budget (`requests_per_second ×
shared_fraction`, adjusted live by AIMD feedback from the rate limiter), rather than either
over-running the rate limit or dropping data outright. A `fixed` mode (floors/pins only, no
stretching, no AIMD) exists as a debugging/transition fallback, not the recommended default.
See [Scheduler Architecture](observability/scheduler.md) for the full mechanism.

**Network filtering enforced at a single choke point.** Every collector that needs a list of
networks goes through `OrganizationInventory.get_networks(org_id)`, which is the sole place
the configured include/exclude `NetworkFilter` (by name glob, ID, or tag) is applied. This is
a structural rule in this codebase, not just a convention — collectors are not permitted to
call `getOrganizationNetworks` directly. For an operator, the practical effect is that
scoping the exporter to a subset of networks (by tag, or by explicit include/exclude lists)
is guaranteed to apply consistently everywhere metrics are produced, rather than needing to
be re-implemented per collector.

**Metric lifecycle / expiration.** Devices and networks that disappear from the Meraki
inventory (decommissioned, removed, renamed) have their previously-emitted series expired
rather than left as permanent stale time series in Prometheus. This matters for exporters
that run for months against a changing estate — without expiration, `/metrics` output only
grows.

**A published metric stability policy.** The [Metric Stability & Deprecation
Policy](stability.md) states, as of the 1.0 release, exactly which metric names, labels, and
units are covered by a compatibility promise across `1.x`, which are marked experimental and
may still change, and how a post-1.0 rename would be handled (old name kept alongside new for
a deprecation window, not a silent breaking change). Building dashboards and alerts against a
documented stability contract is different from building against "whatever fields happen to
exist in the current script."

**OpenTelemetry as a self-observability and product-data layer, not a metrics duplicate.**
The exporter can emit its own OTel traces (collection cycles, API calls) for debugging itself,
and can optionally emit a structured OTel *data-log* channel for high-cardinality per-entity
data (e.g. per-client information) that would be inappropriate as a labelled Prometheus
series — see [Data logs vs. metrics](observability/otel.md#data-logs-vs-metrics-the-boundary-rule)
for the exact boundary rule. There is also an optional, opt-in OTLP metrics bridge that
periodically pushes the existing Prometheus registry to an OTLP metrics endpoint for
operators whose collection pipeline is push-based rather than scrape-based; enabling it does
not change `/metrics` output. Prometheus `/metrics` remains the sole metrics surface — none
of this is a second, parallel metrics system.

**Container image and Helm chart, deliberately no PyPI package.** For v1 this exporter ships
only as a container image plus an official [Helm chart](deployment-operations.md) for
Kubernetes — there is no `pip install`. That is a deliberate scope decision (see
[Deployment & Operations](deployment-operations.md)), not an oversight: it keeps the
supported surface to one artifact type with one dependency set, at the cost of not
supporting a bare-metal/venv install path.

## When to pick this exporter vs a simpler community script

Pick a small single-file community exporter when you have a handful of networks, want to
read and modify the entire collection logic yourself in an afternoon, and don't need
scoping, expiration, or a stability contract — the operational simplicity of "one script, one
process" is a real advantage at that scale.

Pick this exporter when any of the following apply: you run enough networks/devices that
uncoordinated per-device polling risks the Meraki API rate limit; you need to scope
collection to a subset of networks (by tag or name) without hand-rolling that filter
yourself; you want metrics that survive months of inventory churn without accumulating stale
series; you want a documented compatibility guarantee before wiring dashboards/alerts to
specific metric names; or you're deploying into Kubernetes and want a maintained Helm chart
rather than hand-writing a Deployment manifest.

See the [Support Matrix](support-matrix.md) for which device models and metric families are
actually covered today, and the [FAQ](faq.md) for setup and troubleshooting specifics.
