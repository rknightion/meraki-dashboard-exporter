# CLAUDE.md — dashboards/

<system_context>
Hand-maintained Grafana dashboard JSON exports (no generator). The shipped dashboards are
**known-not-good** and are scheduled for a full rebuild in a dedicated future task using
specialist Grafana agents. Until that rebuild happens, treat this directory as frozen.
</system_context>

<critical_notes>
- **Dashboards are OUT OF SCOPE for code fixes.** Never edit `dashboards/*.json` as part of an
  exporter code change (no panel adds/removals/query edits), and never defer or park a code fix
  because it "might break a dashboard" — orphaned/`No data` panels are expected and will be
  handled by the rebuild task.
- Grafana **alerting** is likewise descoped until the dashboard rebuild phase.
- The known dashboard defects are tracked as GitHub issues (search the `bug-bash` +
  `area:observability` labels for the parked findings F-150–F-156). Do not re-discover them.
</critical_notes>

<rebuild_worklist>
## Inputs for the dedicated dashboard-rebuild task

Known defects in the current JSON (validated against the exporter code; each has a GitHub issue):

- **F-150** — org template variable + panels query nonexistent `meraki_org` series; the real
  exported series is `meraki_org_info` (prometheus_client `Info` always emits `<name>_info`).
  Affects organization-overview, network-overview, api-usage-licensing.
- **F-151** — mr-access-points "Radio Configuration" panels filter `band="2.4GHz"`/`"5GHz"` but
  the exporter emits band label values `"2.4"`/`"5"`/`"6"` (matches the OpenAPI enum). No 6 GHz
  query exists at all.
- **F-152** — `rate()` wrapped around windowed-gauge metrics (`meraki_mr_connection_stats_total`
  is a 30-min-window gauge; `meraki_org_usage_{up,down}stream_kb` is a 1-h-window gauge) in 8
  panels across 3 dashboards — semantically meaningless numbers.
- **F-153** — dead `legendFormat` labels that don't exist in the query result in ~10 panels
  across 5 dashboards (e.g. `{{device_name}}` where the label is `name`, `{{collector}} ({{tier}})`
  on gauges that carry neither, `{{org_name}}` on series labelled only `org_id`).
- **F-154** — exact-match `org_id="$organization"` on non-repeat panels while the variable is
  multi-select/All (pipe-joined value never matches). organization-overview panel 9,
  api-usage-licensing panel 3.
- **F-155** — `status="grace_period"` license matcher matches nothing (per-device license states
  are active/expired/expiring/recentlyQueued/unused/unusedActive; co-term overview status is
  "OK"/"expired"-style). Also note co-term orgs are excluded from `status="active"` panels.
- **F-156** — 59 device-specific `meraki_*` metric families appear on no dashboard; the MX/MG/MV
  dashboards show only the 6 generic device metrics. Surface MS stack, MX uplink-loss/VPN,
  MG RSRP, MV people-count, MT gateway-RSSI, etc.
- **Units nuance** (from F-115 live validation): `meraki_ms_port_traffic_bytes` is a
  bytes-per-**second** rate over the poll window, NOT a cumulative byte counter — panels must
  format it as bandwidth (Bps), never wrap it in `rate()`/`increase()` or render as a total.
- General guidance for the rebuild: verify every queried series name + label set against
  `core/constants/metrics_constants.py` / `core/metrics.py::LabelName` (or a live `/metrics`
  scrape) before authoring a panel; prefer generating panels from the exporter's own metric
  metadata rather than hand-typing series names.
</rebuild_worklist>
