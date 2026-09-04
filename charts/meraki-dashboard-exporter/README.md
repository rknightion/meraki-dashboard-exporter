# meraki-dashboard-exporter Helm chart

Deploys the [Meraki Dashboard Exporter](https://github.com/rknightion/meraki-dashboard-exporter) to
Kubernetes. Published to the GHCR OCI registry on every release alongside the container image.

```bash
helm install meraki-dashboard-exporter \
  oci://ghcr.io/rknightion/charts/meraki-dashboard-exporter \
  --version <exporter-version> \
  --set meraki.apiKey=your_api_key_here
```

The render **fails fast** unless exactly one of `meraki.apiKey` / `meraki.existingSecret` is set —
prefer `existingSecret` (or `extraEnv` sourcing a Secret) in production so the key never lands in
`helm get values` / release history. Pod and container run non-root with a read-only root
filesystem, all Linux capabilities dropped, and the ServiceAccount token unmounted by default.

See [`values.yaml`](values.yaml) for the fully-commented, authoritative list of settings.

## Singleton / replicas

The exporter is a **single-writer singleton — it has no leader election.** Every running pod
independently scrapes the Meraki API on the same schedule, so a second replica does not share load;
it doubles the outbound API request rate against the per-org 10 req/s budget and emits a duplicate,
competing set of metrics. Therefore:

- `replicaCount` must be `1` — the chart **hard-`fail`s** the render if it is greater (and if
  `autoscaling.maxReplicas` is greater than `1`).
- The Deployment uses `strategy.type: Recreate`, so a rollout tears down the old pod before starting
  the new one and never briefly runs two pods at once.

## Resource sizing

Memory scales with metric cardinality, which scales with device/network count. It is **not** a
fixed fleet-size value.

**Evidence label: BOOTABLE DEFAULT - NOT A REPRESENTATIVE SIZING MEASUREMENT.** The unchanged
defaults are 100m / 256Mi requests and 500m / 512Mi limits. They are a bootable starting point,
not a supported scale tier. Set requests and limits from a representative measurement with its
topology, enabled collectors, cardinality, and observed RSS recorded; retain headroom for normal
variation. Enabling the clients collector increases cardinality and memory substantially.

**Evidence label: HOMELAB MEASUREMENT ONLY - NOT A REPRESENTATIVE SIZING MEASUREMENT.** The
retained full `ExporterApp` replay is documented in [the scaling guide](../../docs/scaling-guide.md).
It must not be generalized to a medium, large, or dense-switch fleet.

## Optional resources (all disabled by default)

| Value                  | Renders                     | Purpose |
|------------------------|-----------------------------|---------|
| `serviceMonitor.enabled` | Prometheus Operator `ServiceMonitor` | in-cluster scraping |
| `ingress.enabled`      | `Ingress`                   | TLS termination in front of the webhook receiver |
| `networkPolicy.enabled`| `NetworkPolicy`             | restrict pod ingress/egress |
| `autoscaling.enabled`  | `HorizontalPodAutoscaler`   | manage the single pod (unusual — see below) |

### Ingress / webhook TLS

Meraki delivers alert webhooks (`POST /api/webhooks/meraki`) **only over HTTPS**, while the exporter
serves plain HTTP. Enable `config.webhooksEnabled` and front the Service with a TLS terminator — the
bundled Ingress, or an external nginx/Traefik. Terminate TLS there and forward HTTP to the pod; the
receiver URL configured in the Meraki Dashboard must be `https://…/api/webhooks/meraki`. Full
nginx/Traefik/Ingress examples are in
[docs/deployment-operations.md](../../docs/deployment-operations.md). Do **not** expose `/metrics`
publicly via ingress — scrape it in-cluster.

### NetworkPolicy

`networkPolicy.enabled: true` renders a policy that (requires a NetworkPolicy-enforcing CNI):

- **Ingress**: allows the `http` port (metrics scrape + webhook). Restrict the sources via
  `networkPolicy.ingress.from` (standard `from` peers — e.g. the Prometheus namespace/pod selector);
  empty means any source, still port-restricted. Set `networkPolicy.ingress.enabled: false` for an
  egress-only policy.
- **Egress**: DNS (UDP/TCP 53), HTTPS 443 to the Meraki Dashboard API (no fixed CIDR → any
  destination on 443), and the shared OTLP collector port (`networkPolicy.egress.otlpPort`, default
  4317) when **any** tracing (`config.otelEnabled`), data-log (`config.otelLogsEnabled`), or metrics
  (`config.otelMetricsEnabled`) channel is enabled. Use `networkPolicy.egress.extraEgress` for a
  channel using a distinct port, and `networkPolicy.egress.otlpTo` to pin peers for the shared port.

### Autoscaling (unusual)

Because there is no leader election, scaling *replicas* beyond 1 is unsupported. The optional HPA
exists only to let Kubernetes manage the **single** pod against a CPU/memory target — `maxReplicas`
defaults to `1` and the chart fails if you raise it above `1`. When `autoscaling.enabled` is true the
Deployment omits its static `replicas` so the HPA owns it. Most operators should leave this off and
size `resources` directly.
