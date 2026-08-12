# HTTP Endpoints

This page lists HTTP endpoints exposed by the exporter.

| Method | Path | Description | Notes |
|--------|------|-------------|-------|
| `GET` | `/` | Root endpoint with HTML landing page. | Public landing page; UI may be disabled. |
| `POST` | `/api/clients/clear-dns-cache` | Clear the DNS cache through the authenticated control API. | State-changing control API; fail-closed bearer token required, and clients must be enabled. |
| `POST` | `/api/collectors/trigger` | Trigger a collector run through the authenticated control API. | State-changing forced collection; fail-closed bearer token required. |
| `GET` | `/api/metrics/cardinality` | Get cardinality analysis via JSON API. | Read-only cardinality JSON; UI/token-gated when configured. |
| `POST` | `/api/webhooks/meraki` | Meraki webhook receiver endpoint. | Webhook receiver; requires webhooks enabled and validates the configured shared secret. |
| `GET` | `/cardinality` | Get cardinality analysis report in HTML format. | Read-only cardinality UI; UI/token-gated when configured. |
| `GET` | `/cardinality/all-labels` | Get all labels with usage statistics. | Read-only cardinality UI; UI/token-gated when configured. |
| `GET` | `/cardinality/all-metrics` | Get all metrics with cardinality details. | Read-only cardinality UI; UI/token-gated when configured. |
| `GET` | `/cardinality/export/json` | Export cardinality data as JSON. | Read-only cardinality export; UI/token-gated when configured. |
| `GET` | `/cardinality/label-values/{metric_name}` | Get label value distribution for a specific metric. | Read-only cardinality detail; UI/token-gated when configured. |
| `GET` | `/clients` | Client data visualization endpoint. | Read-only client UI; requires clients enabled and is UI/token-gated when configured. |
| `GET` | `/config` | Redacted effective-configuration view (#312). | Read-only redacted configuration; UI/token-gated when configured. |
| `GET` | `/health` | Liveness endpoint with a dead-man switch (F-043). | Public, read-only liveness probe. |
| `GET` | `/metrics` | Prometheus metrics endpoint. | Public, read-only Prometheus scrape endpoint. |
| `GET` | `/ready` | Readiness probe - returns 200 when initial collection is complete. | Public, read-only readiness probe. |
| `GET` | `/status` | Exporter self-health status dashboard. | Read-only status UI; UI/token-gated when configured. |

## Notes

- `/metrics` and `/health` are always available.
- The client UI and DNS cache endpoint are gated by client collection.
- The webhook endpoint returns 404 when webhooks are disabled.

