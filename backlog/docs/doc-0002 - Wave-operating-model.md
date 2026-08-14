---
id: doc-0002
title: Wave operating model
type: guide
created_date: '2026-08-14 16:00'
updated_date: '2026-08-14 16:00'
---
This document carries **only what is true of `meraki-dashboard-exporter`**. The campaign model itself
— run contract and run modes, the routing contract, authority and the thread pool, child lane briefs,
external-contract freezing, the blocker contract, the goal-file template, the run-end protocol and the
pre-flight checklist — is the *Agent fan-out protocol (canonical)* doc, and that doc wins on any
specific. Nothing here restates it. **If a section below could be pasted into another repo unchanged,
it is in the wrong document.**

The protocol is harness-neutral: it describes lanes by **role**, and its Appendix A (Codex) or
Appendix B (Claude Code) resolves a role into a concrete route. Waves on this repo have been written
by Claude and executed by Codex, so **name the harness in the run contract and resolve every lane's
route from that harness's profile** — a lane brief carrying a role name alone is not routed.

Every rule here exists because something failed here. The failure is kept with the rule; a rule
without its reason gets argued away by the next session.

---

## 1. Rules this project added, and what caused each

### Every network fetch goes through `OrganizationInventory.get_networks(org_id)`

That call is the **single enforcement point** for the configured `NetworkFilter`
(`core/network_filter.py`, `NetworkFilterSettings` in `core/config_models.py`). A collector that calls
`getOrganizationNetworks` directly silently collects networks the operator excluded — no error, no
warning, just a wider blast radius and a bigger API bill than the config promises.

Three bypasses are sanctioned and no more may be added without a decision on the tracker:
`core/discovery.py::DiscoveryService` (audit logging, deliberately **unfiltered**), and
`collectors/alerts.py::AlertsCollector._fetch_networks_direct` plus
`core/api_helpers.py::APIHelper._fetch_networks_direct` — both inventory-unavailable fallbacks that
**reapply `NetworkFilter` by hand**. If you add a fallback, it reapplies the filter itself.

### A new per-entity signal goes to the data-log emitter, never to a labelled metric

Prometheus metrics here carry bounded, fleet-shaped aggregates: org, network, device serial, SSID
number, port, band, or a top-N bounded by construction. Anything that fans out per client, per
delivery row or per request goes to `core/otel_data_logs.py` (see
`docs/observability/otel.md#data-logs-vs-metrics-the-boundary-rule`). The measured reason: about **74
live series per switch port**, which projects to ~2.1m series for a LARGE fleet and ~9.5m for XL, on
a registry that `generate_latest(REGISTRY)` serialises whole on one of two serving threads. The
opt-in ID-only client series plus the `meraki_client_info` join is grandfathered and unaffected.

Cardinality work has needed four separate bounding changes already — top-N with an `other` bucket for
client applications, a bounded DNS fan-out, client-store map eviction, and separating the exporter's
own self-instrumentation out of `product_series` (which had been overstating product data by ~18%).
Unboundedness, not volume, is the defect.

### The API is reached through one instrumented facade

One facade acquires a pacing token, records the attempt and owns retries, with project AIMD as the
sole pacer and the SDK's smart flow explicitly off. The failure that forced it: two rate limiters
paced the same traffic without knowing about each other. The failure *after* it: startup discovery
still called the SDK directly, so those calls were **unmetered, unpaced and outside the gate** — a
facade is not a facade until the last direct call site is gone. Scope for anyone repeating this: 141
raw `asyncio.to_thread` call sites at the time.

### Never raw `asyncio.gather` for fan-out

Use `ManagedTaskGroup` or `process_in_batches_with_errors`, both with an explicit `max_concurrency`
tied to `settings.api.concurrency_limit`. The `asyncio.gather` calls that remain are inside those
primitives (`core/async_utils.py`, `core/batch_processing.py`), in `services/dns_resolver.py`'s
bounded producer/worker pool, and one 3-second shutdown drain in `app.py`. A raw `gather` in a
collector is a review failure, not a style preference.

### Metric and label names come from enums, always

`OrgMetricName` / `DeviceMetricName` / `MSMetricName` / `MRMetricName` and friends in
`core/constants/metrics_constants.py`; `LabelName` in `core/metrics.py`. A hardcoded string is how a
metric gets emitted under a name no dashboard queries, which is invisible on both sides.

### Emit through `parent._set_metric()`

Straight to the Prometheus object skips lifecycle tracking, so the series never expires when the
device goes away and a decommissioned device reads healthy forever.

### Wrap new fetchers with `validate_response_format`

The Meraki SDK's exhausted-retry error shape is not the response shape. Four fetches shipped without
this and had to be retro-fitted.

### One organisation per process

The single-org contract is a v1 decision, not an oversight. Multi-org is sharding: N processes, and
the per-source-IP arithmetic in `docs/scaling-guide.md` caps shards per egress IP.

### Work that touches a live system stays with the root agent

Lanes do read-only investigation, code edits, tests and inventory sweeps. **Live Meraki calls, the
soak host, Grafana pushes and anything in another repository stay with the root agent.** This is not
only blast radius: a dispatched lane inherits the parent's permission mode and **cannot clear a soft
block**, because clearing one requires a message from the user and a lane's transcript contains none.
A dispatch brief is explicitly refused as consent. A blocked lane is run by the root agent, never
re-dispatched with better wording.

### Specs and plans are never committed, and no longer enumerate the work

They live in gitignored `docs/superpowers/`. Since this tracker landed the queue is
`backlog task list --plain` and acceptance criteria live on the task, so a plan file restating either
is a second source of truth that drifts. The four files in there as of 2026-08-14 are completion
artefacts for shipped work — the drift-detection plan whose tool is `tools/apidrift/`, and the
bug-bash findings for issues that are all closed. **Do not mine them for tasks.**

### Every in-repo `CLAUDE.md` is a claim to verify, not ground truth

Directly proven: `scripts/CLAUDE.md` once denied the CI docs-drift gate existed, while that gate was
red for **20 consecutive runs over two days** and nobody noticed. `scripts/generate_metrics_docs.py`
excluded a `CircuitBreaker` class that did not exist anywhere in the codebase, and excluded all of
`async_utils.py` for a reason that had evaporated with it. Both are fixed now — and that is the point:
the file said one thing and the tree said another, and the file was believed.

---

## 2. Recurring defects in this codebase

Each of these has shipped at least once. Check for them; do not hope about them.

### A dashboard panel that queries nothing still renders

It loads, it just says "No data" — so nothing fails and nobody notices. This is the single most
repeated defect here, in at least seven distinct forms: a template variable and panels querying
`meraki_org` when the real series is `meraki_org_info`; `band="2.4GHz"`/`"5GHz"` filters against an
exporter that emits `"2.4"`/`"5"`/`"6"`; `legendFormat` referencing labels absent from the result, so
~10 panels across 5 dashboards rendered empty legends; `rate()` over windowed *gauges* in 8 panels
across 3 dashboards, producing meaningless numbers rather than none; an exact-match
`org_id="$organization"` against a multi-select/All variable; a matcher for a license
`status="grace_period"` that no license state ever carries; and 59 `meraki_*` families displayed on no
dashboard at all.

**So a metric or label rename is not done until `grafana/dashboards/*.json` and `grafana/alerts/` are
updated and re-verified against a live scrape.** A removed metric orphans its panel silently — that
happened to a "Collection Wait Time (p95)" panel, which was knowingly left showing No data while the
dashboards were frozen for a rebuild. The freeze is long over; the silent-orphan failure mode is not.

### A generated doc under-reporting looks exactly like a doc with nothing to report

Generators here have shipped ghost settings (`PATH_PREFIX`, `ENABLE_HEALTH_CHECK`,
`CLIENTS__DNS_SERVER`), a wrong `SAMPLING_RATE` claim baked into the generator itself, and a
parse-failure path that swallowed models. They now **exit non-zero on a parse failure**, and the
"Found N…" eyeball checks are assertions. Never hand-edit a generated artefact: change its source and
run `make docgen`. The eight generators are wired through `scripts/generate-docs.sh`, and CI fails the
build when the tree drifts.

### A green local gate is not the same question as a green CI

`make check` did not include `ruff format --check`, so the local gate passed where CI failed —
enforced locally in `353ecfa`. Separately, the weekly slow-tests job was perpetually red because it
collected 0 tests and pytest exits 5 on an empty collection, which reads as a failure rather than as
"nothing selected". Run the real gate and read its output; do not infer.

### A Meraki response field you did not expect to be null is null

`getDeviceAppliancePerformance` returned `None` and raised `DataValidationError: Expected dict, got
NoneType` roughly twice a minute in production. `DataRatesCollector` crashed with a `TypeError` on
null `downloadKbps`/`uploadKbps`, so wireless data-rate metrics were never emitted at all. A benign
404 (no mesh repeaters) was logged twice at ERROR. Model every field as optional, and classify a
404/402 on a license-gated endpoint as "not licensed" — permanent state, never a failure streak.

### A metric that emits once where it should emit per entity

`meraki_mr_clients_connected` returned a single line instead of one per AP. The histogram `le` label
rendered as an int on the OTLP bridge path and a float on the scrape path. **A zero-series metric is
indistinguishable from a metric that never emits** — which is why the data-log emitted/dropped
counters had to be made discoverable.

### An availability check that is racy because it tests state before acquiring it

`collectors/manager.py` tests `collector_lock.locked()` **before** awaiting the semaphore, so
admission is racy. This is the open question in `mde-0001`, and the same non-atomicity was filed
independently during the audit. If you touch admission, the test is a real concurrent run, not a
reading of the code.

---

## 3. Lane conventions

### Single-owner files — never two lanes, never concurrently

These are the frozen seams. A lane needing a new enum gets it added to the seam **first**, by the root
agent or one dedicated seam lane, before fan-out.

- `core/metrics.py` (`LabelName`) and `core/constants/metrics_constants.py` (metric enums) — every
  lane reads them, so a concurrent edit conflicts with all of them at once.
- `core/collector.py`, `core/metric_expiration.py` — base class and lifecycle.
- `core/config_models.py` — the settings tree. Note `.env.example`, `docs/config.md` and the Helm
  `values.yaml`/`configmap.yaml` knob blocks are all **generated from it**, so two lanes editing it
  produce a conflicting regeneration, not just a conflicting diff.
- The coordinators and registries: `collectors/manager.py`, `collectors/device.py`,
  `collectors/organization.py`, `collectors/network_health.py`. Wiring pass only.
- `app.py` — the composition root and every HTTP surface.

### Generated files are never edited by hand

`.env.example`, `docs/config.md`, `docs/metrics/*`, `docs/collectors/*`, `docs/endpoints*`, the
scaling-capacity tables, and the marker-delimited regions of the Helm chart. A lane that changes an
input regenerates with `make docgen` in the same commit. `generate_helm_config.py` **skips
`SecretStr` fields entirely** — a secret must never reach a plaintext ConfigMap — and errors rather
than guessing if its BEGIN/END markers are missing.

### Exclusive resources — one lane at a time, and only from the root agent

- **The live Meraki organisation.** Read-only GETs, narrowly scoped, behind a capability gate that
  first proves the key is valid and the org actually has the hardware in question. The key lives in
  the gitignored `.env`; never print it, never copy it into a fixture, a log, a trace, a commit or a
  transcript. Never a mutating request. Do not turn an exploratory failure into an unbounded probe
  loop. **The org's own rate-limit budget is the shared resource** — two lanes probing at once is
  indistinguishable from the exporter misbehaving.
- **The live soak host.** Root agent only, read-only HTTP and telemetry inspection: no container,
  image, config, watchtower, filesystem or process mutation. It is named only in ignored local
  config, never in a tracked file.
- **The Grafana stack.** Dashboards and alert/recording rules in `grafana/` are authored via `gcx`
  and deployed to the "Meraki Dashboard Exporter" folder; rules go through the Mimir ruler. Verify
  against a live scrape after a metric rename, not against the JSON alone.
- **The shared workflow repository.** `mde-0003` needs changes in `rknightion/.github`. It may be
  inspected read-only; it may not be edited, committed, pushed or have its rulesets changed without
  explicit authority from Rob. A local-only partial gate must not ship.

### Pushing to `main` redeploys the soak, so cross-push counters are not evidence

The soak host runs watchtower against `:main`. A push rebuilds the image, watchtower pulls it and the
container restarts — which is how the 15-hour counters behind `mde-0001` were destroyed before anyone
could read them. Work that depends on soak counters pins a digest or snapshots first.

### A lane that hits a decision its brief does not cover stops and returns the question

It does not invent an answer. One round trip is cheaper than the rewrite. This is the escape hatch for
an ownership map that turns out to be wrong, and it is what makes the single-owner list above safe to
enforce — **a boundary with no escape hatch is a stop condition wearing a safety label.** The specific
things a lane must never decide alone here: a new metric or label name, a cardinality trade-off, a
new sanctioned `NetworkFilter` bypass, and any breaking change to a released metric.

---

## 4. Run-end against this tracker

The tracker *is* the report. There is no run-end file, and `codex/` run artefacts are gitignored
working state that nothing durable may live only in.

- Landed work: `backlog task edit <id> --check-ac N -s Done` **in one call**, with the commit SHA in
  the final summary. Splitting the criteria check from the status change lets an interrupted run leave
  finished work looking unfinished.
- Attempted and blocked: `-s Parked` with a concrete resume boundary — what was tried, what the next
  action is, and what would unblock it. Two of the five migrated tasks have an explicit park
  condition written into their acceptance criteria, because parking is the correct outcome there.
- Untouched work needs no action; it is still `To Do` and self-evidently so.
- Discovered work: a new task labelled `needs-triage`. Never a note in a summary nobody queries.
- Notes and plans are appended (`--append-notes`, `--append-plan`), never set. The bare flags replace
  the whole section silently, and the `PreToolUse` hook in `.claude/hooks/backlog-guard.py` denies
  them.

Before any task goes to `Done`, the `definition_of_done` gate in `backlog/config.yml` must have
actually been run and its output seen: `make check` always, `make docgen` whenever its inputs changed,
and the `grafana/` queries checked whenever a metric or label name moved. Evidence, not assertion.

Work arriving as a **GitHub issue from an outside contributor** becomes an `mde-NNNN` task citing the
issue number; the board, not the issue, is where it is worked. The GitHub tracker stays open for
exactly that.
