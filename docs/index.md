---
title: Meraki Dashboard Exporter
description: High level overview and quick links
image: assets/social-card.png
---

# Meraki Dashboard Exporter

A production-ready Prometheus exporter for the Cisco Meraki Dashboard API. It covers all Meraki device types, includes collector health and cardinality monitoring, and can mirror metrics plus traces via OpenTelemetry.

## Quick start

1. Copy `.env.example` to `.env` and set `MERAKI_EXPORTER_MERAKI__API_KEY`.
2. Run `docker compose up -d` using the [provided compose file](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml).

Or run directly with Docker:
```bash
docker run -d \
  -e MERAKI_EXPORTER_MERAKI__API_KEY=your_api_key_here \
  -p 9099:9099 \
  ghcr.io/rknightion/meraki-dashboard-exporter:latest
```

## Learn more
- [Getting Started](getting-started.md)
- [Configuration](config.md)
- [Deployment & Operations](deployment-operations.md)
- [Integration & Dashboards](integration-dashboards.md)
- [Collectors Overview](collectors/index.md)
- [Metrics Reference](metrics/index.md)
- [OpenTelemetry](observability/otel.md)
