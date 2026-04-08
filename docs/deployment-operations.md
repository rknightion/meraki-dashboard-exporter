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

## Log Aggregation

The exporter outputs structured logs in `logfmt` format by default, which is ideal for Loki ingestion. You can switch to JSON format by setting:

```bash
MERAKI_EXPORTER_LOGGING__FORMAT=json
```

### Grafana Alloy Configuration

To ship logs to Loki using Grafana Alloy, add this to your Alloy configuration:

```alloy
local.file_match "meraki_exporter" {
  path_targets = [{"__path__" = "/var/log/meraki-exporter/*.log"}]
}

loki.source.file "meraki_exporter" {
  targets    = local.file_match.meraki_exporter.targets
  forward_to = [loki.write.default.receiver]
}

loki.write "default" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
```

For Docker or Kubernetes deployments, use the container log discovery instead:

```alloy
discovery.docker "meraki" {
  host = "unix:///var/run/docker.sock"
  filter {
    name   = "name"
    values = ["meraki-dashboard-exporter"]
  }
}

loki.source.docker "meraki" {
  host       = "unix:///var/run/docker.sock"
  targets    = discovery.docker.meraki.targets
  forward_to = [loki.write.default.receiver]
}
```

### Example LogQL Queries

**Collector failures:**
```logql
{container="meraki-dashboard-exporter"} |= "Failed to collect" | logfmt
```

**Rate limit events:**
```logql
{container="meraki-dashboard-exporter"} |= "rate limit" or |= "429" | logfmt
```

**Slow collections (>60s):**
```logql
{container="meraki-dashboard-exporter"} |= "collection_duration" | logfmt | duration > 60
```

**Error summary by collector:**
```logql
sum by (collector) (count_over_time({container="meraki-dashboard-exporter"} |= "error" | logfmt [1h]))
```

For configuration options see the [Configuration](config.md) guide. A list of
exported metrics is available in the [Metrics Reference](metrics/metrics.md).
