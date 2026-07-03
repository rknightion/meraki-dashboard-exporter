# CLAUDE.md

<system_context>
Meraki Dashboard Exporter - A production-ready Prometheus exporter that collects metrics from Cisco Meraki Dashboard API and exposes them for monitoring. Supports OpenTelemetry **traces for self-observability** plus an optional **structured data-log** channel for per-entity product data (both not a metrics mirror — Prometheus `/metrics` remains the sole metrics surface; see `core/otel_tracing.py`, `core/otel_data_logs.py`, and `docs/observability/otel.md`) and includes comprehensive collectors for devices, networks, organizations, and sensor data.
</system_context>

<critical_notes>
- **Navigate to subdirectories** for detailed context - each has its own `CLAUDE.md`
- **No fixed update tiers**: an adaptive scheduler (`core/scheduler.py`) solves each endpoint group's polling interval from its own volatility floor and the API budget; see `core/CLAUDE.md` and `docs/observability/scheduler.md`
- **Security**: Never log or expose API keys, use read-only when possible
- **Memory**: Be mindful of API rate limits and implement proper error handling
- **Use parallel tasks/agents** when suitable use the parallel tasks and agents available to you
- **Git commands are allowed** — committing and pushing (including straight to `main`) is fine when the task calls for it
- **Network fetches go through inventory**: All collectors must use `OrganizationInventory.get_networks(org_id)` so the configured `NetworkFilter` is enforced uniformly. Direct `getOrganizationNetworks` SDK calls in collectors are forbidden. `DiscoveryService` (`core/discovery.py`) deliberately bypasses the filter for audit purposes (the only *unfiltered* bypass). Two other sanctioned direct calls exist, both filtered fallbacks used only when `self.inventory` is `None`, each manually reapplying `NetworkFilter` itself: `AlertsCollector._fetch_networks_direct` (`collectors/alerts.py`) and `APIHelper._fetch_networks_direct` (`core/api_helpers.py`, reached via `APIHelper.get_organization_networks`).
- **Wrap fetchers with `validate_response_format`**: New API fetchers that may receive the SDK exhausted-retry error shape must use `core.error_handling.validate_response_format` to normalize the response.
</critical_notes>

<file_map>
## NAVIGATION MAP - DETAILED CONTEXT IN SUBDIRECTORIES
- `src/meraki_dashboard_exporter/` - Main source package - See `src/meraki_dashboard_exporter/CLAUDE.md`
- `src/meraki_dashboard_exporter/core/` - Core infrastructure - See `src/meraki_dashboard_exporter/core/CLAUDE.md`
- `src/meraki_dashboard_exporter/collectors/` - Collector implementations - See `src/meraki_dashboard_exporter/collectors/CLAUDE.md`
- `src/meraki_dashboard_exporter/collectors/devices/` - Device collectors - See `src/meraki_dashboard_exporter/collectors/devices/CLAUDE.md`
- `src/meraki_dashboard_exporter/collectors/organization_collectors/` - Organization collectors - See `src/meraki_dashboard_exporter/collectors/organization_collectors/CLAUDE.md`
- `src/meraki_dashboard_exporter/collectors/network_health_collectors/` - Network health - See `src/meraki_dashboard_exporter/collectors/network_health_collectors/CLAUDE.md`
- `src/meraki_dashboard_exporter/services/` - Inventory cache, client store, DNS resolver, status service - See `src/meraki_dashboard_exporter/services/CLAUDE.md`
- `src/meraki_dashboard_exporter/api/` - API client wrapper - See `src/meraki_dashboard_exporter/api/CLAUDE.md`
- `tests/` - Test suite and patterns - See `tests/CLAUDE.md`
- `pyproject.toml` - Project dependencies and configuration
- `grafana/` - Grafana **v2-schema** dashboards (`grafana/dashboards/`, 6 consolidated tabbed dashboards) + alerting/recording rules (`grafana/alerts/`). Authored via the `gcx` CLI and deployed to Grafana (folder "Meraki Dashboard Exporter"); rules deploy via `gcx`/Mimir ruler. This replaced the old classic-schema `dashboards/*.json` (removed 2026-07 after the rebuild). See `grafana/CLAUDE.md`.
- `docs/` - Zensical documentation site (NOT MkDocs, despite Make target names) - See `docs/CLAUDE.md`
- `scripts/` - Code generation and documentation scripts - See `scripts/CLAUDE.md`
- `charts/meraki-dashboard-exporter/` - Helm chart - See `charts/meraki-dashboard-exporter/CLAUDE.md`
- `tools/apidrift/` - Standalone Meraki API drift-detection CLI - See `tools/apidrift/CLAUDE.md`
- `.github/` - CI workflows and composite actions - See `.github/CLAUDE.md`
- `evidence/` - v1-readiness assessment evidence pack (verified research backing issues #508–#617; treat as solved data — see `evidence/README.md`)
</file_map>

<paved_path>
## HIGH-LEVEL ARCHITECTURE

### Collector Organization
- **Core Infrastructure**: Logging, config, metrics, error handling -> `src/meraki_dashboard_exporter/core/CLAUDE.md`
- **Collector Pattern**: Auto-registration, endpoint groups/scheduler, base classes -> `src/meraki_dashboard_exporter/collectors/CLAUDE.md`
- **Device-Specific**: MR, MS, MX, MT, MG, MV collectors -> `src/meraki_dashboard_exporter/collectors/devices/CLAUDE.md` (MR's own subpackage has a further nested `devices/mr/CLAUDE.md`)
- **Network Health**: Bluetooth, connection stats, data rates, RF health, SSID performance -> `src/meraki_dashboard_exporter/collectors/network_health_collectors/CLAUDE.md`
- **Organization-Level**: API usage, licensing, client overview -> `src/meraki_dashboard_exporter/collectors/organization_collectors/CLAUDE.md`
- **API Integration**: Async wrapper for Meraki SDK -> `src/meraki_dashboard_exporter/api/CLAUDE.md`
- **Services**: Inventory cache (NetworkFilter enforcement), client store, DNS resolver, status -> `src/meraki_dashboard_exporter/services/CLAUDE.md`
- **Testing**: Factories, mocks, assertions -> `tests/CLAUDE.md`

### Key Principles
- **Domain-specific metric enums**: Use `OrgMetricName`, `DeviceMetricName`, `MSMetricName`, `MRMetricName`, etc. from `core/constants/metrics_constants.py`
- **Label enums**: Use `LabelName` enum from `core/metrics.py`
- **Domain models**: Pydantic validation for all API responses
- **Error handling**: Decorators from `core/error_handling.py`; wrap fetchers with `validate_response_format` to normalize the SDK exhausted-retry error shape
- **Adaptive scheduling, not fixed tiers**: each collector declares one or more endpoint groups (name, priority, `floor_seconds`, `cost_fn`); the scheduler (`core/scheduler.py`) solves each group's actual interval from org shape and the API budget, stretching lower-priority groups when demand exceeds it (default per-collector timeout: 240s)
- **Parallel collection**: Use `ManagedTaskGroup` for bounded concurrency
- **Inventory caching (mandatory for networks)**: All network fetches go through `OrganizationInventory.get_networks(org_id)`; this is the single enforcement point for the configured `NetworkFilter` (`core/network_filter.py`, `NetworkFilterSettings` in `core/config_models.py`).
- **Meraki SDK 3.3.0** (`pyproject.toml`, exact pin — Renovate bumps it, so check `pyproject.toml` rather than trusting this number): `validate_kwargs` setting (`core/config_models.py` `APISettings.validate_kwargs`); recommended for dev/CI, off by default in production.
- **Metric lifecycle**: Track and expire metrics for offline/removed devices
- **Web endpoints**: `app.py` exposes `/metrics`, the web UI, and a `/status` health dashboard endpoint.

</paved_path>

<bash_commands>
## COMMON COMMANDS
- `uv run python -m meraki_dashboard_exporter` - Start the exporter
- `uv run ruff check --fix .` - Lint and auto-fix code
- `uv run ruff format .` - Format code
- `uv run mypy .` - Type checking
- `uv run pytest` - Run tests
- `uv run pytest -v -k test_name` - Run specific test
- `uv add package_name` - Add new dependency
- `make check` - Run all checks (lint, typecheck, test)
- `make docgen` - Generate all documentation
- `make docker-compose-up` - Start with Docker
- `make run-dev` - Run with auto-reload for development
</bash_commands>

<code_style>
## PROJECT-WIDE STYLE GUIDELINES
- **Formatting**: Ruff with 100-char line length (target: py314)
- **Type hints**: Use `from __future__ import annotations` and proper typing
- **Imports**: Relative imports within package (e.g., `from ..core.metrics import LabelName`)
- **Docstrings**: NumPy-style with type hints
- **Constants**: Use StrEnum for metric/label names
- **Early returns**: Reduce nesting where possible
- **Async**: Use `asyncio.to_thread()` for Meraki SDK calls (SDK is synchronous)
</code_style>

<fatal_implications>
## PROJECT-WIDE CRITICAL "DO NOT" RULES
- **NEVER use hardcoded metric/label names** - always use enums
- **NEVER log API keys or sensitive data**
- **NEVER assume API response format** - always validate
- **NEVER skip error handling** for API calls
- **NEVER use `any` types** without explicit justification
- **NEVER modify tests to match incorrect implementations**
- **NEVER commit without running linters and type checks**
- **NEVER work in subdirectories without consulting their `CLAUDE.md`**
- **NEVER use unbounded parallelism** - always use ManagedTaskGroup with max_concurrency
- **NEVER bypass inventory service** - use cached data when available
- **NEVER call `getOrganizationNetworks` directly from a collector** - go through `OrganizationInventory.get_networks(org_id)` so `NetworkFilter` is enforced. Only `core/discovery.py::DiscoveryService` (audit logging, unfiltered), `collectors/alerts.py::AlertsCollector._fetch_networks_direct`, and `core/api_helpers.py::APIHelper._fetch_networks_direct` (both inventory-unavailable fallbacks that reapply `NetworkFilter` manually) are permitted to bypass.
- **NEVER forget metric tracking** - use `parent._set_metric()` for automatic expiration
- **Grafana dashboards + alert/recording rules live in `grafana/`** (v2 schema, authored via `gcx`). They are no longer frozen — the dedicated rebuild landed 2026-07. When a metric/label name changes, update the affected `grafana/dashboards/*.json` queries and re-verify against a live scrape (see `grafana/CLAUDE.md`).
- **NEVER add a new client-keyed (or otherwise unbounded per-entity) labelled Prometheus metric** — metrics carry bounded, fleet-shaped aggregates (org/network/device serial/SSID number/port/band, or top-N bounded by construction); a new per-client/per-entity signal (client ID/MAC, per-delivery row, anything that fans out per-request) routes to the OTel data-log emitter (`core/otel_data_logs.py`, see `docs/observability/otel.md#data-logs-vs-metrics-the-boundary-rule`) instead. The existing opt-in `collectors/clients.py` ID-only numeric series + `meraki_client_info` join (#533) is grandfathered and unaffected by this rule.
</fatal_implications>

<roadmap_workflow>
## IMPLEMENTING A ROADMAP TASK

The prioritised backlog lives in the **GitHub Project** "meraki-dashboard-exporter roadmap"
(https://github.com/users/rknightion/projects/2). Each task is a labelled GitHub **issue** whose body
is a self-contained spec. Point an agent at one issue and follow this exact workflow.

### 1. Load the task
- `gh issue view <N>` (or `gh issue view <N> --json title,body,labels`) to read the full spec.
- The body states: goal/data unlocked, the exact Meraki API endpoint(s) + SDK method, files to touch,
  cardinality/rate-limit notes, and acceptance criteria. Treat those as the contract.
- Read the `CLAUDE.md` of every subdirectory you will touch **before** editing (fatal rule).

### 2. Verify assumptions against reality (do NOT trust the issue blindly)
- Confirm the SDK method exists in the installed `meraki` version: introspect `self.api.<controller>`.
- Confirm the endpoint/response shape against the OpenAPI spec if unsure — the spec may have moved on
  since the issue was written. If the issue is stale, fix the approach and note it in the issue.
- For `v1-readiness`-labelled issues (#508–#617), consult `evidence/` first — it holds the verified
  research (capacity math, per-fetcher conformance tables, live-API samples) backing those issues;
  treat its facts as solved data rather than re-deriving them. Beware: the OpenAPI spec is WRONG for
  some endpoints (see `evidence/live-api-verification.md`) — when an issue flags live verification,
  do it before coding (a working homelab key lives in the gitignored `.env`).
- Check whether the metric/enum already exists (several issues wire up *already-declared* enums).

### 3. Implement (strict TDD)
- Failing test first (see `tests/CLAUDE.md`: factories, mock API, metric assertions) → watch it fail →
  minimal implementation → green → refactor.
- **Metrics:** domain enums only (`OrgMetricName`/`MRMetricName`/… in `core/constants/metrics_constants.py`),
  `LabelName` enums (`core/metrics.py`), Pydantic domain model for the response, wrap the fetcher with
  `core.error_handling.validate_response_format`, emit via `parent._set_metric()` for expiration.
- **Networks:** fetch only via `OrganizationInventory.get_networks(org_id)` (NetworkFilter enforcement).
- **Concurrency:** `ManagedTaskGroup` / `process_in_batches_with_errors` — never raw `asyncio.gather`.
- **Endpoint group:** declare a `floor_seconds` (natural volatility window) and a `priority`
  (1=up-ness/alerts, 2=sensor, 3=perf/health, 4=config/inventory) and justify both; prefer
  org-wide bulk endpoints over per-device/per-network loops to protect the rate-limit budget.
- **Cardinality:** never label by client MAC, raw SSID/BSSID, per-request rows, or other unbounded/
  attacker-influenced values — aggregate to bounded label sets.

### 4. Verify & close
- `make check` (ruff + mypy + pytest) must be green — evidence, not assertion.
- Regenerate docs if metrics/config changed (`make docgen`).
- Reference the issue from the commit (`Closes #<N>`) so the board updates automatically.

### Adding new roadmap tasks
Create an issue with the same body template + labels (`roadmap`, one `area:*`, one `P0`–`P3`), add it to
Project #2, and set the Priority/Area/Effort/Type/Status fields. Priority + milestone express **ordering
only** — there are deliberately no calendar due-dates.

### Working many issues in parallel (wave method)
Proven during the 2026-07 bug-bash burndown (issues #334–#507). Use it whenever a milestone holds
many independent issues.

- **GitHub is the permanent record.** Every piece of work gets a GitHub issue *before* it is fixed,
  and the issue body must be **self-contained** (mechanism + file refs + acceptance criteria) — local
  scratch files vanish; if it isn't in the issue, it doesn't exist.
- **One issue per finding → fix on `main` → close via the commit** (`Closes #<N>`). Tightly-coupled
  issues that are literally one change to one file may share a commit with multiple `Closes` trailers.
- **Validate-before-implement.** Issues were written against a snapshot; re-confirm the mechanism
  against the *current* code, and confirm SDK methods / response shapes against the installed
  `meraki` SDK and the OpenAPI spec before writing the fix. If the issue is stale, say so on the
  issue and close it `wontfix`/`duplicate` rather than forcing a fix.
- **Roles:** the orchestrating main thread owns wave planning, seam/enum decisions, the `make check`
  gate, **all commits and issue closes**. Implementer subagents each own one lane, re-confirm their
  issues, TDD the fix, run scoped tests, and return a self-contained final-message brief.
  **Subagents never commit and never run `gh`.**
- **Lane = a disjoint set of files with ONE owner.** Group issues by the file(s) they touch — two
  issues editing the same file share a lane. Never split a file across concurrent agents.
- **Seams are funnelled, never parallelised.** Shared/high-blast-radius files — `core/metrics.py`
  (LabelName), `core/constants/metrics_constants.py` (metric enums), `core/collector.py`,
  `core/metric_expiration.py`, and coordinators/registries (`device.py`, `organization.py`,
  `network_health.py`, `manager.py`, `config_models.py`) — are edited by the orchestrator or one
  dedicated lane per wave. A lane needing a new enum gets it added to the frozen seam first.
- **Foundational seams first (wave 0), then fan out.** Transient red mid-wave is fine; the full
  `make check` must be green at each wave's integration checkpoint and before every commit.
- **Scale the swarm to the risk:** docs/DX waves tolerate many cheap parallel lanes; code waves that
  share seams run fewer, more careful lanes.
</roadmap_workflow>
