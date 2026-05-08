---
title: Meraki Dashboard Exporter
description: High level overview and quick links
image: assets/social-card.png
---

# Meraki Dashboard Exporter

!!! warning "Limited testing"

    I no longer have access to a Meraki network with anything other than MT (sensor) devices. Changes affecting other device types (MS, MR, MX, MG, MV) are best-effort — vibecoded from publicly available API documentation and SDK references rather than tested against live hardware.

A production-ready Prometheus exporter for the Cisco Meraki Dashboard API. It covers all Meraki device types, includes collector health and cardinality monitoring, and supports OpenTelemetry tracing.

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
