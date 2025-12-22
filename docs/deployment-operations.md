---
title: Deployment & Operations
description: Running the exporter in production
---

# Deployment & Operations

This exporter is distributed as a container image. The repository contains a [docker-compose.yml](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml) with sane defaults. Adjust the environment variables in your `.env` file and start the stack:

```bash
docker compose up -d
```

## Endpoints
- `/` – landing page with runtime status
- `/health` – basic liveness
- `/metrics` – scrape endpoint for Prometheus
- `/cardinality` – HTML report (plus `/api/metrics/cardinality` for JSON)
- `/cardinality/all-metrics` and `/cardinality/all-labels` – detailed views
- `/cardinality/export/json` – full JSON export
- `/cardinality/label-values/{metric_name}` – label value distribution
- `/clients` – client inventory UI (only when `MERAKI_EXPORTER_CLIENTS__ENABLED=true`)
- `/api/clients/clear-dns-cache` – clear DNS cache (clients enabled)
- `/api/webhooks/meraki` – webhook receiver (only when `MERAKI_EXPORTER_WEBHOOKS__ENABLED=true`)

Cardinality endpoints show a “waiting for initial collection” message until the first full collection cycle completes (default: 15 minutes). See the [HTTP Endpoints](reference/endpoints.md) reference for details.

## Monitoring
Scrape `http://<host>:9099/metrics` with Prometheus. Example job:
```yaml
scrape_configs:
  - job_name: meraki
    static_configs:
      - targets: ['meraki-dashboard-exporter:9099']
```

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
