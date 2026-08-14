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
- `evidence/` - v1-readiness assessment evidence pack (the research behind the old issues #508–#617; the record of what was already assessed, baselined 2026-07 — see `evidence/README.md`)
- `backlog/` - **the task tracker.** `backlog task list --plain` is the queue, `backlog doc list --plain` the durable docs. Driven only through the `backlog` CLI; `backlog/config.yml` is the sole hand-edited file. See "Task tracking" below.
- `archive/` - the deleted GitHub Issues, captured as redacted JSON. What `#NNN` resolves to now — see `archive/README.md`.
- `.claude/` - only `settings.json` and `hooks/` are tracked; they wire the Backlog.md guard hook. Everything else there is per-machine state and gitignored.
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
- **Meraki SDK 4.4.0** (`pyproject.toml`, exact pin — Renovate bumps it, so check `pyproject.toml` rather than trusting this number): `validate_kwargs` setting (`core/config_models.py` `APISettings.validate_kwargs`); recommended for dev/CI, off by default in production.
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
- `backlog task list --plain` - The queue. `-m v1.1-hardening` filters to that programme
- `backlog task view <id> --plain` - One task's full spec, criteria and gate
- `backlog doc list --plain` / `backlog doc view <id> --plain` - The durable docs, loaded on demand
- `python3 .claude/hooks/backlog-guard_test.py` - Re-test the tracker guard hook after editing it
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

## Task tracking — Backlog.md

Open work lives in `backlog/`, driven **only** through the `backlog` CLI. `backlog task list --plain`
is the queue; `backlog doc list --plain` lists the durable docs. **GitHub Issues was retired as this
project's tracker on 2026-08-14**, after 449 closed issues, and the issues authored by the maintainer
and by CI were archived and then **deleted from GitHub** — so `gh issue view <N>` 404s for them.
Historical work is still cited as `#NNN` everywhere: in 901 commits, in these instruction files and in
code comments. The *Closed GitHub issues* doc is the index, and `archive/` holds every body and reply
(redacted; `archive/README.md` carries the placeholder mapping). New work is `mde-NNNN`. Two ID
spaces, no overlap. The GitHub Project board "meraki-dashboard-exporter roadmap" is likewise retired.

**The GitHub tracker itself is still open, deliberately** — external contributors must be able to file,
and it is the channel D16 relies on for sanitised real API responses from device families nobody here
owns. Renovate keeps its dependency dashboard there. Anything arriving that way becomes an `mde-NNNN`
task citing the issue number; the board, not the issue, is where it is worked.

Four docs, loaded on demand via `backlog doc view <id> --plain`, so none costs context until read:

- **Agent fan-out protocol (canonical)** — read before designing a wave. Imported verbatim and
  harness-neutral: it routes lanes by **role**, and its Appendix A (Codex) or Appendix B (Claude Code)
  resolves a role into a concrete route. Name the harness in the run contract.
- **Wave operating model** — this project's own rules, restating nothing from the protocol:
  single-owner files, exclusive resources, the recurring defects in this codebase, run-end here.
- **Hardening programme standing decisions (D1-D18)** — frozen decisions and carried-forward
  corrections from the 2026-08 audit burndown. Read before re-proposing anything in that space.
- **Closed GitHub issues: pre-Backlog history index** — what `#NNN` refers to.

Tracker rules, each of which exists because the upstream behaviour is silent and unrepairable:

- **`backlog/` is committed, so no real identifiers in tasks or docs.** No email addresses, handles,
  usernames, org or account IDs, device serials, MACs, host names or credential values — write the
  shape, not the instance ("the live soak host", not its name). Aggregate counts, timings and
  structural findings are fine. A tracker *feels* private, which is exactly why this breaks by
  accident.
- **Never use `--notes` or `--plan` bare** — they *silently replace* the whole section, destroying
  another session's writes with no warning at exit 0. Use `--append-notes` and `--append-plan`. The
  `PreToolUse` hook at `.claude/hooks/backlog-guard.py` denies the bare forms; it ships with its own
  negative-tested suite (`backlog-guard_test.py`, 16 cases).
- **Finalize in one call**, so an interrupted run cannot leave finished work looking unfinished:
  `backlog task edit mde-0001 --check-ac 1 --check-ac 2 -s Done`.
- **Never hand-edit task, draft, doc, decision or milestone markdown.** Section boundaries are
  HTML-comment markers; break one and the section is *silently dropped* at exit 0 — still in the file,
  invisible to the CLI — until the next write destroys it for real. There is no repair command;
  `backlog doctor` only fixes duplicate task IDs. `backlog/config.yml` is the one file edited by hand,
  because list-valued keys cannot be set through `backlog config set`.
- **Never let two agents edit the same task.** The v1.50 concurrency fix covers the edit funnel but
  *not* reorder, draft saves, the TUI edit path, `doc update` or decision updates.
- **`Parked` is a real status**, not a synonym for To Do: attempted, blocked, and left with a concrete
  resume boundary. Flattening it loses the most valuable thing a long autonomous run produces.
- **Do not build on decisions, and do not use the MCP surface.** Decisions are half-built upstream — no
  `edit`, `view` or `update`, no supersede mechanism, no validation — so durable reference goes in
  **docs** and tasks stay the unit. MCP is frozen upstream and costs 10-50k tokens of permanent context
  against 1-2k for the CLI.

<roadmap_workflow>
## IMPLEMENTING A TASK

### 1. Load the task
- `backlog task view <id> --plain` for the full spec, including its acceptance criteria and the
  `definition_of_done` gate it inherited from `backlog/config.yml`.
- The description states: mechanism with `file:line` refs, the exact Meraki endpoint(s) + SDK method
  where relevant, cardinality/rate-limit notes, and any authority boundary. Treat those as the
  contract.
- Read the `CLAUDE.md` of every subdirectory you will touch **before** editing (fatal rule). Note
  Codex does not read those — this file is the harness-independent contract.

### 2. Verify assumptions against reality (do NOT trust the task blindly)
- Confirm the SDK method exists in the installed `meraki` version: introspect `self.api.<controller>`.
- Confirm the endpoint/response shape against the OpenAPI spec if unsure — the spec may have moved on
  since the task was written. If the task is stale, fix the approach and `--append-notes` saying so.
- `evidence/` holds the 2026-07 v1-readiness research (capacity math, per-fetcher conformance tables,
  live-API samples) behind the old `#508–#617` issues. It is the record of **what was already
  assessed**, not current truth: it was baselined at `f08cd69`, spec 1.72.0, SDK 3.3.0. Beware also
  that the OpenAPI spec is WRONG for some endpoints (`evidence/live-api-verification.md`) — when a task
  calls for live verification, do it before coding (a working key lives in the gitignored `.env`).
- Check whether the metric/enum already exists — several tasks only wire up *already-declared* enums.

### 3. Implement (test-first where a test earns its keep)
- Bug fixes and behavioural contracts: failing test first (see `tests/CLAUDE.md`: factories, mock API,
  metric assertions) → watch it fail for the intended reason → minimal implementation → green.
  Validate declarative changes (workflows, Helm, docs, measurements) with their own parsers and
  renderers instead of manufacturing a unit test.
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

### 4. Verify & finalize
- The `definition_of_done` gate in `backlog/config.yml` must have been **run and its output seen** —
  `make check` always, `make docgen` when its inputs changed, and the `grafana/` queries checked when a
  metric or label name moved. Evidence, not assertion.
- Commit straight to `main`, one commit per deliverable, Conventional Commits (release-please and
  Renovate parse the subject). Cite the task ID in the commit.
- Then finalize **in one call**: `backlog task edit <id> --check-ac 1 --check-ac 2 -s Done`, with the
  commit SHA in the final summary. Blocked instead? `-s Parked` with a concrete resume boundary.

### Adding new tasks
`backlog task create` with a self-contained description (mechanism + `file:line` + why) and acceptance
criteria as `--ac` flags, one `area:*` label and a priority label. Assign a milestone only when the task
belongs to a programme. Priority and milestone express **ordering only** — there are deliberately no
calendar due-dates. Work discovered mid-run gets a task labelled `needs-triage`, never a note in a
summary nobody queries.

### Working many tasks in parallel
The wave method lives in the two campaign docs, which is why it is not restated here: read the **Agent
fan-out protocol (canonical)** doc for the model, and the **Wave operating model** doc for this repo's
single-owner files, exclusive resources and frozen seams. Two rules are worth stating even so, because
breaking them is how waves fail here: the orchestrating thread owns **every commit and every tracker
write**, and a lane that hits a decision its brief does not cover **stops and returns the question**
instead of inventing an answer.
</roadmap_workflow>

<!-- BACKLOG.MD GUIDELINES START -->
<!-- backlog.md-instructions-version: 1.50.1 -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**For every user request in this project, run `backlog instructions overview` before answering or taking action.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Before task lifecycle actions, read the matching detailed guide:
- `backlog instructions task-creation` before creating or splitting tasks
- `backlog instructions task-execution` before planning, changing status or assignee, adding a plan or implementation notes, or implementing task work
- `backlog instructions task-finalization` before checking acceptance criteria, writing final summaries, or moving tasks to terminal statuses

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->
