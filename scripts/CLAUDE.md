<system_context>
Documentation generator scripts. Each script statically analyzes the source tree (mostly via `ast`, not by importing/running collector code) and overwrites a committed documentation or configuration artefact. They are invoked by `just gen` / the `just docs-*` recipes and by the docs-sync CI trigger (`.github/workflows/trigger-docs-sync.yml` watches `scripts/**`). See `docs/CLAUDE.md` for which generated files must never be hand-edited.
</system_context>

<critical_notes>
- **Run `just gen` after any change to collectors, config models, metrics, or FastAPI endpoints** — these scripts are the only thing that keeps committed documentation and configuration artefacts in sync with the code, and CI regenerates them and fails when the generated paths drift.
- **`generate_config_docs.py` documents an explicit list of settings models** (`get_nested_models()`), rather than deriving its headings. The generator validates that this list exactly matches the top-level `Settings` tree that `.env.example` walks, so add the corresponding `(title, config_models.NewSettings, "MERAKI_EXPORTER_PREFIX", description)` tuple when adding a settings section; generation fails if you omit it.
- **`generate_config_docs.py` also has a hand-written `section_notes` dict** (freeform caveats per section, e.g. the `Network Filter Settings` include/exclude resolution rules) and one fully hand-typed table row under "Additional Runtime Options" (`MERAKI_EXPORTER_OTEL__SAMPLING_RATE`, read directly from the environment rather than through Pydantic) — both need manual upkeep, they are not derived from code. (The old `Update Intervals` section/note was removed with the tier system, #631 — there is no `UpdateIntervals` model any more.)
- **Three scripts have hardcoded "known exception" dicts at the top that need updating when you add a new conditional/experimental feature:**
  - `generate_collector_docs.py`: `COLLECTOR_NOTES` (e.g. `ClientsCollector` needs `MERAKI_EXPORTER_CLIENTS__ENABLED=true`)
  - `generate_metrics_docs.py`: `EXCLUDED_CLASS_NAMES` (metrics defined but not yet wired up, e.g. `SpanMetricsAggregator`), `CONDITIONAL_NOTES` (feature-flagged owners), `INTERNAL_OWNERS` (owners to label as internal-only, e.g. `CollectorManager`)
  - `generate_endpoints_docs.py`: `ENDPOINT_NOTES` (per-path caveats) and `CARDINALITY_NOTE` (applied to all `/cardinality*` routes)
- **None of these scripts import the package** — they parse source with the stdlib `ast` module (except `generate_config_docs.py`, which does `importlib` a single isolated module, `core/config_models.py`, to introspect real Pydantic `FieldInfo` for types/defaults/constraints). Parse failures and empty metric/collector scans fail generation rather than producing incomplete documentation; CI also regenerates and diffs the generated files.
</critical_notes>

<file_map>
- The root `justfile`'s `gen` recipe is the orchestrator; it runs config, **env-example**, **helm-config**, scaling-capacity, metrics, collectors, endpoint generators and documented-env validation via `uv run python`. The retired shell orchestrator no longer exists. The docs-sync workflow still watches `scripts/**`.
- `generate_config_docs.py` - loads `core/config_models.py` via `importlib` (isolated exec, not a package import) and walks the explicit `get_nested_models()` list of Pydantic settings classes with `generate_model_docs()`, extracting field type/default/constraints (`ge`/`gt`/`le`/`lt`/`min_length`/`max_length`/`pattern`) into a table per section. It validates the list against `Settings` before writing `docs/config.md`.
- `generate_env_example.py` - writes the repo-root **`.env.example`** from the config models. It auto-derives its sections by walking the top-level `Settings` model (`core/config.py`) — every settable env var is emitted, commented at its default (required fields uncommented with an empty value), field description as a comment. It reuses `generate_config_docs.py`'s `find_repo_root`/`extract_constraints` (imported as a module). `SECTION_TITLES` only prettifies headers; a missing entry falls back to the upper-cased field name.
- `generate_helm_config.py` - writes the Helm chart's **config knobs** from the config schema. Walks the top-level `Settings` model (same drift-proof approach as `generate_env_example.py`, reusing its `load_settings_model`/`format_default`/`is_model`/`constraint_suffix`) and splices two BEGIN/END-marked regions: a commented, `# --`-documented knob list into `charts/meraki-dashboard-exporter/values.yaml` (under `config: {}`) and a `{{- with .Values.config }}` + `hasKey`-guarded `MERAKI_EXPORTER_*` env mapping into `templates/configmap.yaml`. Friendly camelCase keys are algorithmic (camelCase of the env suffix) with a small `NAME_OVERRIDES` map for legacy names; `EXCLUDE` skips the three vars wired from higher-level chart values (`MERAKI__API_KEY`, `MERAKI__ORG_ID`, `SERVER__PORT`), and **`SecretStr` fields are skipped entirely** (they must never land in a plaintext ConfigMap — inject via `extraEnv` from a Secret). Both files carry the markers already; **the generator errors if the markers are missing** rather than guessing where to write. Guarded by `tests/test_helm_config_drift.py` (fails if the chart drifts from the schema or a secret leaks in). Set/frozenset defaults are sorted for deterministic output.
- `generate_scaling_capacity_docs.py` - AST-parses `NetworkHealthCollector.endpoint_groups`, evaluates its restricted cost-function shape for HOMELAB and large-org fixtures, and replaces the marker-delimited network-health capacity region in `docs/scaling-guide.md`. It fails if the source shape or markers are absent; the generated region separates steady-state equivalents from a simultaneous due sweep.
- `generate_metrics_docs.py` - AST-walks `src/` for `Gauge(...)`/`Counter(...)`/`Histogram(...)`/`Info(...)` instantiations (two visitor classes, `CreateMetricVisitor` and `PrometheusMetricVisitor`, cover two different construction patterns used in the codebase), resolves metric-name and label-name references back to the `*MetricName`/`LabelName` enum constants in `core/constants/*_constants.py` and `core/metrics.py`, categorizes by owning class, and writes a summary + per-collector tables to `docs/metrics/metrics.md`.
- `generate_collector_docs.py` - AST-walks `src/meraki_dashboard_exporter/collectors/` for class definitions, detects the `@register_collector` decorator (no-arg since #631 — there is no tier argument to resolve any more) to flag auto-registered "main" collectors vs. sub-collectors, and groups unregistered sub-collectors by directory (`collectors/devices/`, `collectors/network_health_collectors/`, `collectors/organization_collectors/`). Writes `docs/collectors/reference.md`.
- `generate_endpoints_docs.py` - AST-walks for functions decorated with `@app.get/post/put/delete/patch/options/head(...)`, using the first line of the docstring as the description. Writes `docs/reference/endpoints.md`.
- `validate_documented_env_vars.py` - validates exact `MERAKI_EXPORTER_*` leaf variables in customer-facing README/docs/chart prose and manifests against the recursively walked `Settings` tree. Generated config/changelog pages are excluded; wildcard/model-prefix prose is not treated as a leaf example.
</file_map>

<paved_path>
## REGENERATE EVERYTHING
```bash
just gen
```

## REGENERATE ONE DOC
```bash
just docs-config       # docs/config.md
just docs-env          # .env.example
just docs-helm         # Helm config regions
just docs-scaling      # docs/scaling-guide.md region
just docs-metrics      # docs/metrics/metrics.md
just docs-collectors   # docs/collectors/reference.md
just docs-endpoints    # docs/reference/endpoints.md
```

## ADDING A NEW SETTINGS SECTION TO config.md
1. Add the new `*Settings` model to `core/config_models.py` as usual.
2. Add a tuple to `get_nested_models()` in `generate_config_docs.py`: `("Section Title", config_models.NewSettings, "MERAKI_EXPORTER_PREFIX", "One-line description")`.
3. Optionally add a freeform caveat to `section_notes` keyed by the same title.
4. Run `just docs-config` and check the diff.

## ADDING A CONDITIONAL/FEATURE-FLAGGED COLLECTOR, METRIC OWNER, OR ENDPOINT
Add an entry to the relevant hardcoded notes dict (`COLLECTOR_NOTES`, `CONDITIONAL_NOTES`, `ENDPOINT_NOTES`) so the generated docs surface the required env var — the generators have no way to infer this from code alone.
</paved_path>
