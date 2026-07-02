---
title: Deployment & Operations
description: Running the exporter in production
---

# Deployment & Operations

This exporter is distributed as a container image, plus an official Helm chart for Kubernetes. Use the [Getting Started](getting-started.md) guide for initial setup and the provided [docker-compose.yml](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml) as a baseline for production deployments.

## Kubernetes (Helm)

A Helm chart ([`charts/meraki-dashboard-exporter`](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/charts/meraki-dashboard-exporter))
is published to the GHCR OCI registry on every release, alongside the container image:

```bash
helm install meraki-dashboard-exporter \
  oci://ghcr.io/rknightion/charts/meraki-dashboard-exporter \
  --version <exporter-version> \
  --set meraki.apiKey=your_api_key_here
```

Chart versions track exporter release versions (e.g. `0.31.0`); an edge chart tracking `main` is
also published on every push, versioned `0.0.0-main.*`. The chart defaults to a hardened
`securityContext` (non-root, read-only root filesystem) and fails render-time validation unless
exactly one of `meraki.apiKey` / `meraki.existingSecret` is set — prefer `existingSecret` in
production. See [`values.yaml`](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/charts/meraki-dashboard-exporter/values.yaml)
for the full set of configurable settings.

## Endpoints
The exporter exposes endpoints for metrics (`/metrics`), liveness (`/health`),
readiness (`/ready`), an exporter self-health dashboard (`/status`), cardinality
reports (`/cardinality`), and optional client (`/clients`) and webhook
(`POST /api/webhooks/meraki`) features. See the [HTTP Endpoints](reference/endpoints.md)
reference for the authoritative list and enablement notes.

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
- Metrics `meraki_exporter_collector_errors_total` help identify failing collectors.
- Open `/status` for an at-a-glance view of tier health and last collection
  durations. Network filter resolution is not shown on `/status` yet (tracked in
  [#311](https://github.com/rknightion/meraki-dashboard-exporter/issues/311)) —
  check the `meraki_network_filter_*` metrics instead (see
  [Network Filter](#network-filter) below).

## Network Filter
For large organisations, restrict scraping to a subset of networks via the
`MERAKI_EXPORTER_NETWORK_FILTER__*` settings (include/exclude by name glob, ID,
or tag). The filter is inactive by default; if a filter is configured but
resolves to zero networks across all configured orgs at startup, the exporter
exits with an error so typos fail loudly. See `.env.example` and the
[Configuration](config.md) guide for details.

## Log Aggregation

The exporter outputs structured logs in `logfmt` format only, which is ideal for Loki ingestion.
There is currently no setting to switch to JSON output — adding a `log_format` setting is tracked in
[#310](https://github.com/rknightion/meraki-dashboard-exporter/issues/310).

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
{container="meraki-dashboard-exporter"} |~ "rate limit|429" | logfmt
```

**Slow collections (utilization warnings, logged when a collector uses >80% of its tier interval):**
```logql
{container="meraki-dashboard-exporter"} |= "Collector utilization high" | logfmt | duration > 60
```

**Error summary by collector:**
```logql
sum by (collector) (count_over_time({container="meraki-dashboard-exporter"} |= "error" | logfmt [1h]))
```

For configuration options see the [Configuration](config.md) guide. A list of
exported metrics is available in the [Metrics Reference](metrics/metrics.md).
