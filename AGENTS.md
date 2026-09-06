# meraki-dashboard-exporter

Prometheus exporter for the Cisco Meraki Dashboard API.

## Surfaces and the boundary between them

- Prometheus `/metrics` is the **sole metrics surface**. OpenTelemetry carries traces for
  self-observability (`core/otel_tracing.py`) and an optional structured data-log channel for
  per-entity product data (`core/otel_data_logs.py`). Neither is a metrics mirror.
- Never add a new client-keyed, or otherwise unbounded per-entity, labelled Prometheus metric.
  Metrics carry bounded fleet-shaped aggregates (org, network, device serial, SSID number, port,
  band, or a top-N bounded by construction). A per-client, per-request or per-delivery signal goes
  to the data-log emitter instead, see
  `docs/observability/otel.md#data-logs-vs-metrics-the-boundary-rule`. The opt-in
  `collectors/clients.py` ID-only numeric series and its `meraki_client_info` join are
  grandfathered and unaffected.
- `app.py` also serves the web UI, `/status`, `/health`, `/ready`, `/clients`, `/config` and a
  small `/api/*` POST surface.

## Collector invariants

- **No fixed polling tiers.** A collector declares endpoint groups (name, `priority`,
  `floor_seconds`, `cost_fn`) and `core/scheduler.py` solves each group's interval from org shape
  and the API budget, stretching lower-priority groups when demand exceeds it. Priorities are
  1 up-ness/alerts, 2 sensor, 3 perf/health, 4 config/inventory. Prefer org-wide bulk endpoints
  over per-device or per-network loops to protect the rate-limit budget.
- **Every network fetch goes through `OrganizationInventory.get_networks(org_id)`**, the single
  enforcement point for `NetworkFilter` (`core/network_filter.py`, `NetworkFilterSettings` in
  `core/config_models.py`). A direct `getOrganizationNetworks` call from a collector is forbidden.
  Exactly three sites are sanctioned: `core/discovery.py::DiscoveryService` (startup audit, the one
  deliberately **unfiltered** bypass), and the two inventory-unavailable fallbacks
  `collectors/alerts.py::AlertsCollector._fetch_networks_direct` and
  `core/api_helpers.py::APIHelper._fetch_networks_direct`, each of which reapplies `NetworkFilter`
  itself.
- **Wrap a new fetcher with `core.error_handling.validate_response_format`.** The SDK's
  exhausted-retry error shape otherwise reaches the parser looking like a response.
- Metric and label names come from the enums (`core/constants/metrics_constants.py`, `LabelName`
  in `core/metrics.py`), never a string literal. Emit through `parent._set_metric()` so expiry
  tracking for offline and removed devices works.
- Concurrency is `ManagedTaskGroup` (`core/async_utils.py`) or `process_in_batches_with_errors`
  (`core/batch_processing.py`), never a raw `asyncio.gather`.
- The Meraki SDK is synchronous: reach it through `asyncio.to_thread()`.
- Every API response gets a Pydantic domain model.

## Verifying against the live API

- **The vendored OpenAPI spec is wrong for some endpoints** (`evidence/live-api-verification.md`).
  Where a change hinges on a response shape, verify against the live API before coding. A working
  key sits in the gitignored `.env`.
- Confirm an SDK method exists in the installed `meraki` version by introspecting
  `self.api.<controller>`, rather than trusting a task description or the spec.
- `evidence/` is the v1-readiness research pack: the record of what was already assessed at the
  baseline `evidence/README.md` states, not current truth.

## Gate

`just check` is exactly what the CI `test` job enforces, and `backlog/config.yml` names it in
`definition_of_done` alongside two conditional legs: `just gen` when metrics, config, endpoints,
collectors, the settings schema or the chart config changed, and the `grafana/` dashboard and rule
queries when a metric or label name moved. Generated artefacts are committed and are overwritten
silently, with no banner in the file, so a hand-edit is lost at the next `just gen`.

Recipes marked `[confirm]` push a multi-arch image to ghcr.io or prune the machine-wide buildx
cache. Stop and ask; never pass `--yes` or `JUST_YES=1`. Run `just` with stdin from `/dev/null`.

Commits are Conventional Commits: release-please and Renovate parse the subject. Cite the task ID.

## Tracker

Open work is `mde-NNNN` in `backlog/`. Historical `#NNN` citations are GitHub issues that were
deleted, so `gh issue view <N>` 404s for them. `archive/github-issues-2026-08-14.json` holds every
body and reply, redacted with stable placeholders; `archive/README.md` carries the mapping, the
verification method and the jq recipes. Two ID spaces, no overlap.

**The GitHub Issues tracker itself stays open, deliberately.** External contributors need a
channel, and it is how sanitised real API responses arrive for device families nobody here owns.
Every surviving issue is somebody else's: never close or delete one. An issue arriving that way
becomes an `mde-NNNN` task citing the number, and the board, not the issue, is where it is worked.

- **`backlog/` is committed, so no real identifiers in tasks or docs.** No email addresses,
  handles, usernames, org or account IDs, device serials, MACs, host names or credential values.
  Write the shape, not the instance ("the live soak host", not its name). Aggregate counts,
  timings and structural findings are fine. A tracker feels private, which is why this breaks by
  accident.
- **Bare `--notes` and `--plan` silently replace the whole section**, destroying another session's
  writes with no warning at exit 0. Use `--append-notes` and `--append-plan`.
- Finalize in one call, so an interrupted run cannot leave finished work looking unfinished:
  `backlog task edit mde-0001 --check-ac 1 --check-ac 2 -s Done`.
- Section boundaries in tracker markdown are HTML-comment markers. Break one by hand-editing and
  the section is silently dropped at exit 0, still in the file but invisible to the CLI, until the
  next write destroys it for real. There is no repair command; `backlog doctor` only fixes
  duplicate task IDs. `backlog/config.yml` is the one file edited by hand, because list-valued
  keys cannot be set through `backlog config set`.
- Never let two agents edit the same task. The concurrency fix covers the edit funnel, not
  reorder, draft saves, the TUI edit path, `doc update` or decision updates.
- `Parked` is a real status: attempted, blocked, and left with a concrete resume boundary. It is
  not a synonym for To Do, and flattening it loses the most valuable thing a long autonomous run
  produces.
- Do not build on decisions, and do not use the MCP surface. Decisions are half-built upstream (no
  edit, view or update, no supersede mechanism, no validation), so durable reference goes in docs
  and tasks stay the unit. MCP is frozen upstream and costs 10-50k tokens of permanent context
  against 1-2k for the CLI.
- New tasks carry a self-contained description (mechanism, `file:line`, why), acceptance criteria
  as `--ac` flags, one `area:*` label and a priority label. Priority and milestone express
  ordering only; there are deliberately no calendar due-dates. Work discovered mid-run gets a task
  labelled `needs-triage`, never a note in a summary nobody queries.

## Deeper references

- `src/meraki_dashboard_exporter/collectors/` and its subpackages - read before adding or changing
  a collector, a device family or a network-health metric.
- `src/meraki_dashboard_exporter/core/` - read before touching the scheduler, error handling, the
  config models, the API helper or metric registration.
- `src/meraki_dashboard_exporter/services/` - read before changing inventory caching, the client
  store, DNS resolution or the status service.
- `tests/` - read before writing a test: factories, the mock API and the metric assertions.
- `docs/` - read before editing a doc page; it lists which committed artefacts are generated and
  by which script.
- `grafana/` - read before editing a dashboard or an alerting or recording rule.
- `scripts/` - read before changing a generator.
- `charts/meraki-dashboard-exporter/` - read before changing the Helm chart.
- `.github/` - read before changing a workflow or a composite action.
- `tools/apidrift/` - read before changing the Meraki API drift-detection CLI.
