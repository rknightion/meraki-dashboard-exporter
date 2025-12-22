---
title: Deployment & Operations
description: Running the exporter in production
---

# Deployment & Operations

This exporter is distributed as a container image. Use the [Getting Started](getting-started.md) guide for initial setup and the provided [docker-compose.yml](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml) as a baseline for production deployments.

## Endpoints
The exporter exposes endpoints for metrics, health, cardinality reports, and optional client/webhook features. See the [HTTP Endpoints](reference/endpoints.md) reference for the authoritative list and enablement notes.

## Monitoring
Prometheus and Grafana integration examples live in the [Integration & Dashboards](integration-dashboards.md) guide.

## Updating
Pull the latest image and restart the container:
```bash
docker compose pull
docker compose up -d
```

## Troubleshooting
- Check container logs with `docker compose logs meraki_dashboard_exporter`.
- Verify the API key and network connectivity.
- Metrics `meraki_collector_errors_total` help identify failing collectors.

For configuration options see the [Configuration](config.md) guide. A list of
exported metrics is available in the [Metrics Reference](metrics/metrics.md).
