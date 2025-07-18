---
title: Meraki Dashboard Exporter
description: High level overview and quick links
---

# Meraki Dashboard Exporter

A lightweight Prometheus exporter for the Cisco Meraki Dashboard API. It collects metrics for organisations and all device types and can forward data via OpenTelemetry.

## Quick start

### Docker
1. Copy `.env.example` to `.env` and set `MERAKI_API_KEY`.
2. Run `docker compose up -d` using the [provided compose file](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml).

### Python
1. `uv pip install meraki-dashboard-exporter`
2. Set `MERAKI_API_KEY`
3. `python -m meraki_dashboard_exporter`

## Learn more
- [Getting Started](getting-started.md)
- [Configuration](config.md)
- [Deployment & Operations](deployment-operations.md)
- [Integration & Dashboards](integration-dashboards.md)
 - [Metrics Reference](metrics/index.md)
