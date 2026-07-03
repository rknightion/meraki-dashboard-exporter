# CLAUDE.md — grafana/

<system_context>
Grafana **v2-schema** dashboards and alerting/recording rules for the exporter, authored with the
`gcx` CLI (Grafana's agent CLI) and deployed to Grafana Cloud. This directory REPLACED the old
`dashboards/*.json` (classic schema, known-broken) in the 2026-07 rebuild. `grafana/dashboards/`
holds the six consolidated, tabbed dashboards; `grafana/alerts/` holds alerting + recording rules.
</system_context>

<layout>
- `dashboards/` — six v2 (`dashboard.grafana.app/v2alpha1`) dashboards, one file each, exported clean via gcx:
  - `self-observability.json` — exporter health: Collectors | Scheduler | API & Rate Limiting | Traces | Logs (spans Prometheus + Tempo + Loki datasources).
  - `meraki-devices.json` — Overview | MR | MS | MX | MT | MV (NO MG). Uses v2 `conditionalRendering` + hidden `has_mx`/`has_mt`/`has_mv` QueryVariables to hide device-type tabs when the selected org has none.
  - `meraki-organization.json`, `meraki-network-health.json`, `meraki-clients.json`.
  - `meraki-client-telemetry.json` — Loki data-log dashboard; mostly "No data" pending issue #637 (signal_quality/packet_loss never emit); Webhook Delivery tab is live.
- `alerts/` — `alerting-rules.yaml` (15 alerts, a de-templated mirror of the chart's `PrometheusRule` — the chart is the source of truth for K8s deploys; change BOTH together) + `recording-rules.yaml` (5 derived `meraki:*` series).
</layout>

<critical_notes>
- **Author/redeploy with gcx** (see the `create-dashboard` bundled skill): edit the JSON → `gcx resources validate -p <file>` → `gcx dashboards create/update <slug> -f <file> --api-version dashboard.grafana.app/v2alpha1` → `GCX_AGENT_MODE=true gcx dashboards snapshot <slug> --output-dir <dir> --theme dark` → **inspect the PNG** → iterate. Re-export clean: `gcx dashboards get <slug> --api-version dashboard.grafana.app/v2alpha1 -o json --jq '{apiVersion,kind,metadata:{name:.metadata.name,annotations:{"grafana.app/folder":"meraki-exporter"}},spec}'`.
- **Datasource variable gotcha**: the `datasource` DatasourceVariable's `current.value` must be the datasource **UID** (`grafanacloud-prom`), with `regex:""` — a name-regex filters out all options (the ds *name* is `grafanacloud-robknight-prom`, not the UID).
- **Query every metric via the SCRAPE path**: filter `job="meraki_dashboard"` on EVERY panel query + `label_values`. In a soak/multi-instance setup the same series is ALSO written under the OTLP-bridge jobs (`meraki-dashboard-exporter[-devnet]`); without the filter, sums/rates/joins double- or triple-count.
- **Filter orgs with regex** `org_id=~"$organization"` (never exact `=` — breaks on multi-select/All).
- **Verify metric + label names live before authoring a panel** (`gcx metrics query 'group by(__name__)(...)'`, `group by(<label>)(<metric>)`). The pre-v1 rename changed names; do not trust old query strings.
- **Alert deploy**: `alerting-rules.yaml`/`recording-rules.yaml` are Mimir-ruler format — deploy via `mimirtool rules load` (recording rules are not a Grafana-managed-alerting concept, so `gcx alert` can't push them; `gcx alert` is read-only). For K8s, the chart's `PrometheusRule` covers the alerts.
</critical_notes>
