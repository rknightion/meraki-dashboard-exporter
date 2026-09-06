# grafana/

Grafana dashboards (`dashboards/`) and Mimir-ruler alerting plus recording rules (`alerts/`) for
the exporter. Dashboards are v2 schema, `apiVersion: dashboard.grafana.app/v2alpha1`, authored and
deployed with the `gcx` CLI.

## Authoring loop

Edit the JSON, then:

    gcx resources validate -p <file>
    gcx dashboards create|update <slug> -f <file> --api-version dashboard.grafana.app/v2alpha1
    GCX_AGENT_MODE=true gcx dashboards snapshot <slug> --output-dir <dir> --theme dark

Inspect the rendered PNG and iterate; a dashboard that validates and pushes can still render wrong.
Re-export clean with:

    gcx dashboards get <slug> --api-version dashboard.grafana.app/v2alpha1 -o json \
      --jq '{apiVersion,kind,metadata:{name:.metadata.name,annotations:{"grafana.app/folder":"meraki-exporter"}},spec}'

The folder annotation is `meraki-exporter`; a re-export that drops it files the dashboard at the
root.

## Query traps

- **The `datasource` DatasourceVariable's `current.value` must be the datasource UID**
  (`grafanacloud-prom`) with `regex: ""`. The datasource *name* is `grafanacloud-robknight-prom`,
  so a name-shaped regex filters out every option and the variable comes up empty.
- **Filter `job="meraki_dashboard"` on every panel query and every `label_values`.** In a soak or
  multi-instance setup the same series is also written under the OTLP-bridge jobs
  (`meraki-dashboard-exporter`, `meraki-dashboard-exporter-devnet`); without the filter, sums,
  rates and joins double- or triple-count silently.
- Filter orgs with `org_id=~"$organization"`, never exact `=`: exact match breaks on multi-select
  and on All.
- Verify metric and label names against the live stack before authoring a panel
  (`gcx metrics query 'group by(__name__)(...)'`, `group by(<label>)(<metric>)`). Old query strings
  in an existing dashboard are not proof a name still exists.

## Device tabs

`meraki-devices.json` hides device-family tabs the selected org has no hardware for, using v2
`conditionalRendering` driven by hidden `has_mx` / `has_mt` / `has_mv` QueryVariables. Adding a
family means adding both the variable and the rendering condition; a tab with neither is always
visible.

`self-observability.json` spans the Prometheus, Tempo and Loki datasources in one dashboard.

## Rules

- `alerts/alerting-rules.yaml` is a de-templated mirror of the chart's `PrometheusRule`. The chart
  is the source of truth for Kubernetes deploys, so change both together.
- Both rule files are Mimir-ruler format: deploy with `mimirtool rules load`. Recording rules are
  not a Grafana-managed-alerting concept so `gcx alert` cannot push them, and `gcx alert` is
  read-only in any case.
