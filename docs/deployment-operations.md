---
title: Deployment & Operations
description: Running the exporter in production
---

# Deployment & Operations

This exporter is distributed as a container image. The repository contains a [docker-compose.yml](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml) with sane defaults. Adjust the environment variables in your `.env` file and start the stack:

```bash
docker compose up -d
```

## Health checks
- `/health` – basic liveness
- `/ready` – exporter has successfully collected data

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
