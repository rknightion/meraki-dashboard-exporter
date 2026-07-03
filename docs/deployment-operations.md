---
title: Deployment & Operations
description: Running the exporter in production
---

# Deployment & Operations

This exporter is distributed as a container image, plus an official Helm chart for Kubernetes. Use the [Getting Started](getting-started.md) guide for initial setup and the provided [docker-compose.yml](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml) as a baseline for production deployments.

## Distribution

For v1, the exporter ships as a **container image + Helm chart only** — there is no PyPI
package, and `pip install meraki-dashboard-exporter` is not a supported install path. If you
need to run it outside a container, clone the repository and run it with `uv` as described in
[Getting Started](getting-started.md).

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

The exporter is a **single-writer singleton** (no leader election), so `replicaCount` must stay `1`
— the chart hard-fails the render otherwise, and its Deployment uses the `Recreate` strategy so a
rollout never briefly runs two pods. Optional resources, all off by default: `ingress.enabled`
(webhook TLS termination, see below), `networkPolicy.enabled` (locks egress to DNS + Meraki API 443
+ the OTLP port), `serviceMonitor.enabled` (Prometheus Operator), and `autoscaling.enabled` (an HPA
that manages the single pod; `maxReplicas` is capped at 1). Read the `resources:` sizing guidance in
`values.yaml` before deploying at scale — the 512Mi default is sized for small orgs only.

### Shutdown behaviour and grace period

On `SIGTERM`, the exporter starts an orderly shutdown: in-flight HTTP requests are allowed to
finish and running collector work is given a chance to wind down before the process exits. This
is **best-effort, not guaranteed**, because collector fetches run the synchronous Meraki SDK on a
background thread pool (`asyncio.to_thread`, sized by `executor_workers`) — a thread genuinely
blocked inside an SDK HTTP call cannot be cancelled mid-flight from the asyncio event loop, so
shutdown has to wait for that call to return (either normally or via its own timeout) rather than
being able to kill it instantly.

Two settings bound how long a single blocked fetch can hold things up:

- `single_request_timeout` (`MERAKI_EXPORTER_API__TIMEOUT`, default `30s`) bounds one HTTP request
  to the Meraki API.
- `per_fetch_deadline_seconds` (default `120s`, not yet exposed as a chart value) bounds a whole
  logical fetch, including every page requested under `total_pages="all"` pagination — so a bulk
  fetch that keeps making slow page requests still fails fast at 120s instead of hanging for the
  full per-collector timeout.

Kubernetes only gives a pod `terminationGracePeriodSeconds` after `SIGTERM` before force-killing it
with `SIGKILL`. If that grace period is shorter than the worst-case blocked fetch, Kubernetes kills
the pod mid-shutdown, which is harmless (the exporter is stateless and safely restartable) but shows
up as noisy `SIGKILL`/`terminated: Error` events instead of a clean exit. The Helm chart's
[`terminationGracePeriodSeconds`](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/charts/meraki-dashboard-exporter/values.yaml)
value defaults to **150s** — comfortably above the `per_fetch_deadline_seconds` default (120s) with
a ~30s margin (matching `single_request_timeout`) for the deadline to actually fire and the fetch to
unwind before Kubernetes gives up. If you raise `per_fetch_deadline_seconds` above its default (via
`extraEnv`, e.g. `MERAKI_EXPORTER_API__PER_FETCH_DEADLINE_SECONDS`), raise
`terminationGracePeriodSeconds` to match — as a rule of thumb, keep it at
`per_fetch_deadline_seconds + ~30s`.

## Endpoints
The exporter exposes endpoints for metrics (`/metrics`), liveness (`/health`),
readiness (`/ready`), an exporter self-health dashboard (`/status`), cardinality
reports (`/cardinality`), and optional client (`/clients`) and webhook
(`POST /api/webhooks/meraki`) features. See the [HTTP Endpoints](reference/endpoints.md)
reference for the authoritative list and enablement notes.

## Webhook receiver (HTTPS / TLS termination)

The exporter can receive Meraki alert webhooks (`config.webhooksEnabled: true`, endpoint
`POST /api/webhooks/meraki`). **Meraki only delivers webhooks over HTTPS** — it rejects plain
`http://` receiver URLs — but the exporter itself serves plain **HTTP**. So you must terminate
TLS in front of it and forward HTTP to the exporter. The receiver URL you configure in the Meraki
Dashboard (Network-wide → Alerts → Webhooks) must therefore be `https://…/api/webhooks/meraki`,
never `http://`. Always set the shared secret (`MERAKI_EXPORTER_WEBHOOKS__SECRET`) so payloads are
validated — in the Helm chart, inject it via `extraEnv` (sourced from a Secret) rather than a plain
value.

Pick whichever terminator fits your environment; all three terminate TLS and proxy plain HTTP to
the exporter's service port (`9099` by default).

### Kubernetes Ingress (bundled in the Helm chart)

The chart ships an optional Ingress (`ingress.enabled: true`) that fronts the Service. Terminate
TLS at the ingress (e.g. via cert-manager) and it forwards HTTP to the exporter:

```yaml
# values.yaml
config:
  webhooksEnabled: "true"
extraEnv:
  - name: MERAKI_EXPORTER_WEBHOOKS__SECRET
    valueFrom:
      secretKeyRef:
        name: meraki-webhook-secret
        key: secret
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: meraki-exporter.example.com
      paths:
        - path: /api/webhooks/meraki
          pathType: Prefix
  tls:
    - secretName: meraki-exporter-tls
      hosts:
        - meraki-exporter.example.com
```

Meraki receiver URL: `https://meraki-exporter.example.com/api/webhooks/meraki`.

### nginx (standalone reverse proxy)

```nginx
server {
    listen 443 ssl;
    server_name meraki-exporter.example.com;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    # Only expose the webhook receiver publicly; scrape /metrics in-cluster/privately.
    location /api/webhooks/meraki {
        proxy_pass http://meraki-dashboard-exporter:9099;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Traefik (IngressRoute / dynamic config)

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: meraki-exporter-webhook
spec:
  entryPoints:
    - websecure          # the TLS entrypoint
  routes:
    - match: Host(`meraki-exporter.example.com`) && PathPrefix(`/api/webhooks/meraki`)
      kind: Rule
      services:
        - name: meraki-dashboard-exporter
          port: 9099      # plain HTTP to the exporter
  tls:
    certResolver: letsencrypt
```

In every case Meraki talks HTTPS to the terminator, and the terminator talks HTTP to the exporter.

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

### Alerting on partial collection failures

A collector cycle can **succeed overall** — `/ready` stays `200`, and the coordinator does not
raise — while one or more *sub-phases* inside it fail and are silently tolerated. This is
deliberate resilience (a single broken endpoint, e.g. one MX VPN fetch or one org's config
sub-collection, must never abort the rest of that cycle's collection), but it means the honest
top-level failure signals introduced for [#509](https://github.com/rknightion/meraki-dashboard-exporter/issues/509)
(a raised `_collect_impl()`, `/ready` flipping, `meraki_exporter_org_collection_status`) can stay
green for cycles that are nonetheless degraded.

Every one of those tolerated sub-phase failures increments the same counter used for full
collector failures — **`meraki_exporter_collector_errors_total`** (labels: `collector`, `tier`,
`error_type`) — so it is the only signal that surfaces this class of degradation. Alert on its
rate rather than waiting for a full-cycle failure:

```promql
# Any tolerated sub-phase failure in the last 15 minutes, broken out by
# collector/tier/error_type so you can see which sub-system is degraded.
sum by (collector, tier, error_type) (
  rate(meraki_exporter_collector_errors_total[15m])
) > 0
```

```promql
# Sustained partial failure: a collector/tier has logged errors continuously
# for the last hour. Good candidate for a paging alert (vs. the query above,
# which is better suited to a dashboard panel or a low-severity notification).
min_over_time(
  (sum by (collector, tier) (rate(meraki_exporter_collector_errors_total[15m])) > 0)[1h:]
) == 1
```

Because this counter increments for tolerated *and* fatal failures alike, corroborate a firing
alert against the [#509](https://github.com/rknightion/meraki-dashboard-exporter/issues/509) health
signals before treating it as critical:

- `up{job="meraki-dashboard-exporter"}` / `/health` - process liveness (unaffected either way).
- `/ready` and its backing readiness gate - only trips for a **total** cycle failure in a FAST or
  MEDIUM tier collector (SLOW tier is excluded from readiness by design).
- `meraki_exporter_org_collection_status{org_id="..."}` - per-organization gauge, `0` only when
  *every* sub-collection failed for that org this cycle (see `OrganizationCollector`/`OrgHealthTracker`
  in `core/org_health.py`).

If `meraki_exporter_collector_errors_total` is climbing but `/ready` is `200` and
`meraki_exporter_org_collection_status` is `1`, the cycle is completing with **partial** data loss
for the affected sub-phase (e.g. one MR/MS/MX sub-collection, one config sub-collection, or one
org's sensor gateway connections) - worth investigating, but not an outage. If `/ready` also flips
or the org status gauge drops to `0`, treat it as the higher-severity, already-covered #509 failure
case instead.

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
