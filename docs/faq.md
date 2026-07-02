---
title: FAQ
description: Frequently asked questions about running, configuring, and securing the Meraki Dashboard Exporter, each answer pointing to the authoritative documentation page.
tags:
  - faq
  - troubleshooting
  - configuration
---

# Frequently Asked Questions

Short answers to common questions. Each answer links to the authoritative page for the full
detail - treat those linked pages as the source of truth.

## Getting started

### How do I run the exporter?

Run the published Docker image with your Meraki API key set via
`MERAKI_EXPORTER_MERAKI__API_KEY`, then scrape `http://<host>:9099/metrics`. The full quickstart,
including the `.env` file and a `docker run` example, is in [Getting
Started](getting-started.md).

### What do I need before I start?

Docker and a Meraki Dashboard API key (read-only is recommended). See [Getting
Started](getting-started.md) for the requirements and setup steps.

### Which port does it listen on?

`9099` by default. It is configurable via `MERAKI_EXPORTER_SERVER__PORT`. See
[Configuration](config.md).

## Configuration

### How is the exporter configured?

Entirely through environment variables prefixed with `MERAKI_EXPORTER_`, using `__` as the nested
delimiter (e.g. `MERAKI_EXPORTER_API__TIMEOUT`). Every key, its type, and its default is listed
in the generated [Configuration](config.md) reference.

### Should I run one instance per organization?

Yes - the recommended deployment model is one exporter instance per Meraki organization, pinned
with `MERAKI_EXPORTER_MERAKI__ORG_ID`. If the org ID is left unset the exporter polls every
organization the API key can see. See [Upgrading](upgrading.md#single-org-deployment-contract)
for the contract and [Configuration](config.md) for the key.

### How do I limit which networks are collected?

Use the network-filter settings (include/exclude by name glob, ID, or tag). The keys are
documented in the [Configuration](config.md) reference.

### How do I tune it for a large deployment?

Concurrency limits, rate-limit settings, and cardinality caps all scale with your inventory. The
[Scaling Guide](scaling-guide.md) gives concrete per-scale values.

## Metrics

### What metrics does it expose, and how are they named?

Metrics are exposed on `/metrics` in Prometheus format. Naming conventions (base-SI units, the
`_count` / `_total` / bare-plural suffix meanings, label conventions) are explained in the
[Metrics Overview](metrics/overview.md), and the exhaustive per-metric list is the generated
[Complete Metrics Reference](metrics/metrics.md).

### Why don't my numeric metrics carry the org/network/device name?

By design. Mutable name labels are kept off numeric series and exposed on id-keyed `*_info` join
metrics instead, so a rename doesn't orphan time series. Join to the info metric on the ID to
pull names back into a query. See the [Metrics Overview](metrics/overview.md) and the [Metric
Stability & Deprecation Policy](stability.md#name-labels-are-not-part-of-numeric-series).

### Can I rely on metric names not changing?

Stable metric families keep their names, labels, and base units across the 1.x series;
Experimental families may change at any time. Which families are Stable vs Experimental, and how
post-1.0 renames are handled, is the [Metric Stability & Deprecation Policy](stability.md).

### A metric I used was renamed - where is that documented?

Breaking metric changes and deprecations are announced in the [Changelog](changelog.md). The
one-time pre-1.0 rename sweep and how to migrate queries is in [Upgrading](upgrading.md).

## Security

### Is my API key safe in logs and metrics?

The exporter never logs or exposes the API key. Read-only keys are recommended. The full security
posture - container hardening, image signing, and handling of secrets - is in
[Security](security.md).

### How do I verify the image I'm deploying?

Release images and Helm charts are signed; verification steps are in [Security](security.md).

## Upgrading

### How do I upgrade safely?

Read the [Changelog](changelog.md) for the target version, pin a `vX.Y.Z` tag, and roll out. The
exporter is stateless, so there is no migration step. Full guidance, including the 1.0 breaking
sweep, is in [Upgrading](upgrading.md).
