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
- The Meraki SDK is synchronous: reach it only through `core.api_facade.facade_for(owner).call(...)` (see `api/AGENTS.md`); a direct `asyncio.to_thread()` or `run_in_executor()` on an SDK method is forbidden.
- Every API response gets a Pydantic domain model.
- **Never log or echo a Meraki API key**, and never widen a log line or an error path in a way that
  could carry one.

## Verifying against the live API

- **The vendored OpenAPI spec is wrong for some endpoints** (`evidence/live-api-verification.md`).
  Where a change hinges on a response shape, verify against the live API before coding. A working
  key sits in the gitignored `.env`.
- `evidence/` is the v1-readiness research pack: the record of what was already assessed at the
  baseline `evidence/README.md` states, not current truth.

## Task interface

Generated artefacts carry no banner and are overwritten silently by `just gen`; never hand-edit them.

**`test` is not the only required job. Anything touching the `Dockerfile`, the entrypoint or the
image's runtime shape is gated by `docker-build-test`, which `just check` does not cover** - run
`just ci` (`check image image-verify image-structure smoke`) instead. Three separate places assert
the image's runtime contract and all of them are outside `just check`: `image-verify` requires
`Config.User` to be exactly `exporter` (the F-119 deploy guard), `.github/container-structure-test.yaml`
asserts `metadataTest.user`, the entrypoint, the exposed port and the shipped paths, and `smoke`
boots the container and requires `/health` and `/metrics` to answer 200. A green `just check` on a
Dockerfile change means nothing. `image-structure` needs `container-structure-test` on `PATH`;
without it locally, `gcr.io/gcp-runtimes/container-structure-test` over the docker socket is
equivalent.

The publication Trivy gate is stricter still and runs only in `publish.yml`, never in CI: it fails
the build on any HIGH or CRITICAL not accepted in `.trivyignore.yaml`. It blocks the image and chart
push while release-please still creates the tag and the GitHub release, so a release can exist with
no artefact behind it. `scripts/validate_trivy_exceptions.py` validates an exception's shape, not
whether its purls match anything in the current base image, so exceptions silently stop applying
when the base image's distro changes.

The Alpine CA bundle, application certifi and base-interpreter pip vendoring are separate
security surfaces. Runtime removes unused base pip: pip 26.2.2 patches certifi but still vendors
vulnerable urllib3 2.7.0. Keep pip absent unless the whole vendored dependency set is verified.
Inspect the base interpreter with `/usr/local/bin/python`; runtime PATH selects the application venv.

Recipes marked `[confirm]` push a multi-arch image to ghcr.io or prune the machine-wide buildx
cache. Stop and ask; never pass `--yes` or `JUST_YES=1`. Run `just` with stdin from `/dev/null`.

Commits are Conventional Commits: release-please and Renovate parse the subject. Cite the issue as `#N`.

## Tracking work

Work is tracked in this repository's GitHub issues; they are the only queue. Do not add a checklist
file beside them.

- A pull request body says how it relates to an issue, on a line of its own: `Closes #N` with the
  `Acceptance evidence` table from `.github/pull_request_template.md` (one row for each acceptance
  criterion of that issue), `Refs #N` when it only relates to one, or `Task: none, <reason>`.
- A pull request that changes `.github/workflows/` or `.github/actions/` carries no closing keyword:
  write `Task: none, <reason>`, with `Refs #N` beside it if you like.
- Contributors never need the project board or the tracker tooling; a maintainer handles both.
- Issues and pull requests are public, so they carry no real identifiers: no email addresses,
  handles, usernames, org or account ids, device serials, MACs, host names or credential values.
  Write the shape, not the instance ("the live soak host", not its name).
- **The issue tracker stays open, deliberately.** External contributors need a channel, and it is
  how sanitised real API responses arrive for device families nobody here owns. Never close, edit
  or delete an issue somebody else filed, and put no closing keyword in a commit message.
- Older commits, docs and tests cite legacy board ids such as `MDE-0001`. `just issue <ID>` prints
  the issue each one became; `.github/tracker/id-map.json` is the map. The board's documents are
  under `.github/tracker/history/`.
- Historical `#NNN` citations from before 2026-08-14 are GitHub issues that were deleted, so
  `gh issue view <N>` may 404 for them. `archive/github-issues-2026-08-14.json` holds every body
  and reply, redacted with stable placeholders; `archive/README.md` carries the mapping, the
  verification method and the jq recipes.
- New issues carry a self-contained description (mechanism, `file:line`, why), the acceptance
  criteria as an `Acceptance criteria` list, one `area:*` label and a priority label. Work found
  mid-run is filed as an issue labelled `needs-triage`, never left in a summary nobody reads.

## Review and architecture map

- Before committing a non-trivial change, run `just review` and read `.review/report.md`: duplication
  and complexity the change introduced. Advisory; act on what is real.
- `.groma/` is a Groma C4 map of `src/`: one component per package or module, curated descriptions.
  Change it through the CLI (`npx -y groma.md@<groma_version> ...`); `agent-instructions` prints the
  guides. `just groma-check` gates CI and the loop: it fails when a non-test module under `src/` is
  added or deleted without a rescan. Fix: `just groma-scan`, fold a new file's component into its
  package's with `groma edit <component> --combine <new-id>`, and commit `.groma/` with the change.
- Relationships are authored and anchored on files; the scanner derives none, so a changed call goes
  unnoticed. Deleting a module that is the only file of a component anchoring relationships leaves a
  stale reference the CLI cannot remove: run `groma view <file>` before deleting a module, and if it
  happens, hand-edit only that stale code reference out of `.groma/`.

## Deeper references

- `src/meraki_dashboard_exporter/collectors/` and its subpackages - read before adding or changing
  a collector, a device family or a network-health metric.
- `src/meraki_dashboard_exporter/core/` - read before touching the scheduler, error handling, the
  config models, the API helper or metric registration.
- `src/meraki_dashboard_exporter/services/` - read before changing inventory caching, the client
  store, DNS resolution or the status service.
- `src/meraki_dashboard_exporter/api/` - read before changing how the SDK client is constructed;
  it carries the `APISettings.validate_kwargs` contract (default off, turn it on in dev and CI).
- `tests/` - read before writing a test: factories, the mock API and the metric assertions.
- `docs/` - read before editing a doc page; it lists which committed artefacts are generated and
  by which script.
- `grafana/` - read before editing a dashboard or an alerting or recording rule.
- `scripts/` - read before changing a generator.
- `charts/meraki-dashboard-exporter/` - read before changing the Helm chart.
- `.github/` - read before changing a workflow or a composite action.
- `tools/apidrift/` - read before changing the Meraki API drift-detection CLI.
