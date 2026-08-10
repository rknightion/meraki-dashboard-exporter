---
title: Meraki Dashboard Exporter
description: High level overview and quick links
image: assets/social-card.png
---

# Meraki Dashboard Exporter

!!! warning "Limited testing"

    I no longer have access to a Meraki network with anything other than MT, MR & MS devices. Changes affecting other device types (MX, MG, MV) are best-effort and driven from publicly available API documentation and SDK references rather than tested against live hardware. See the [Support Matrix](support-matrix.md) for exactly what is collected per product line.

A production-ready Prometheus exporter for the Cisco Meraki Dashboard API. It covers all Meraki device types, includes collector health and cardinality monitoring, and supports OpenTelemetry tracing.

## Quickstart

With a Meraki Dashboard API key (read-only is enough):

```bash
docker run -d \
  -e MERAKI_EXPORTER_MERAKI__API_KEY=your_api_key_here \
  -p 9099:9099 \
  ghcr.io/rknightion/meraki-dashboard-exporter:latest
```

Metrics are then at `http://localhost:9099/metrics`.

## Get started

Start with the [Getting Started](getting-started.md) guide for the fastest setup, then review
[Configuration](config.md) to tune the exporter for your environment.

## Learn more
- [Getting Started](getting-started.md)
- [Configuration](config.md)
- [Deployment & Operations](deployment-operations.md)
- [Integration & Dashboards](integration-dashboards.md)
- [Collectors Overview](collectors/index.md)
- [Metrics Reference](metrics/index.md)
- [OpenTelemetry](observability/otel.md)
