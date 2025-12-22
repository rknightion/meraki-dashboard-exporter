# HTTP Endpoints

This page lists HTTP endpoints exposed by the exporter.

| Method | Path | Description | Notes |
|--------|------|-------------|-------|
| `GET` | `/` | Root endpoint with HTML landing page. |  |
| `POST` | `/api/clients/clear-dns-cache` | Clear the DNS cache. | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `GET` | `/api/metrics/cardinality` | Get cardinality analysis via JSON API. | Cardinality data appears after the first collection cycle (defaults to the SLOW interval). |
| `POST` | `/api/webhooks/meraki` | Meraki webhook receiver endpoint. | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |
| `GET` | `/cardinality` | Get cardinality analysis report in HTML format. | Cardinality data appears after the first collection cycle (defaults to the SLOW interval). |
| `GET` | `/cardinality/all-labels` | Get all labels with usage statistics. | Cardinality data appears after the first collection cycle (defaults to the SLOW interval). |
| `GET` | `/cardinality/all-metrics` | Get all metrics with cardinality details. | Cardinality data appears after the first collection cycle (defaults to the SLOW interval). |
| `GET` | `/cardinality/export/json` | Export cardinality data as JSON. | Cardinality data appears after the first collection cycle (defaults to the SLOW interval). |
| `GET` | `/cardinality/label-values/{metric_name}` | Get label value distribution for a specific metric. | Cardinality data appears after the first collection cycle (defaults to the SLOW interval). |
| `GET` | `/clients` | Client data visualization endpoint. | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `GET` | `/health` | Health check endpoint. |  |
| `GET` | `/metrics` | Prometheus metrics endpoint. |  |

## Notes

- `/metrics` and `/health` are always available.
- The client UI and DNS cache endpoint are gated by client collection.
- The webhook endpoint returns 404 when webhooks are disabled.

