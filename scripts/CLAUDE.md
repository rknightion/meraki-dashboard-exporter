<system_context>
Documentation generator scripts. Each script statically analyzes the source tree (mostly via `ast`, not by importing/running collector code) and overwrites one file under `docs/` with a regenerated Markdown reference. They are invoked by `make docgen` / the `make docs-*` targets and by the docs-sync CI trigger (`.github/workflows/trigger-docs-sync.yml` watches `scripts/**`). See `docs/CLAUDE.md` for which generated files must never be hand-edited.
</system_context>

<critical_notes>
- **Run `make docgen` (or `./scripts/generate-docs.sh`) after any change to collectors, config models, metrics, or FastAPI endpoints** — these scripts are the only thing that keeps `docs/` in sync with the code; nothing else regenerates them and there's no CI check that fails if they drift.
- **`generate_config_docs.py` documents a HARDCODED list of settings models** (`nested_models` in `generate_configuration_docs()`), not a walk of the whole config tree. Adding a new `*Settings` model to `core/config_models.py` does **nothing** to the docs unless you also add a `(title, config_models.NewSettings, "MERAKI_EXPORTER_PREFIX", description)` tuple to that list.
- **`generate_config_docs.py` also has a hand-written `section_notes` dict** (freeform caveats per section, e.g. the `Update Intervals` ordering constraint) and one fully hand-typed table row under "Additional Runtime Options" (`MERAKI_EXPORTER_OTEL__SAMPLING_RATE`, read directly from the environment rather than through Pydantic) — both need manual upkeep, they are not derived from code.
- **Three scripts have hardcoded "known exception" dicts at the top that need updating when you add a new conditional/experimental feature:**
  - `generate_collector_docs.py`: `COLLECTOR_NOTES` (e.g. `ClientsCollector` needs `MERAKI_EXPORTER_CLIENTS__ENABLED=true`)
  - `generate_metrics_docs.py`: `EXCLUDED_CLASS_NAMES` / `EXCLUDED_FILES` (metrics defined but not yet wired up, e.g. `SpanMetricsAggregator`, `CircuitBreaker`), `CONDITIONAL_NOTES` (feature-flagged owners), `INTERNAL_OWNERS` (owners to label as internal-only, e.g. `CollectorManager`)
  - `generate_endpoints_docs.py`: `ENDPOINT_NOTES` (per-path caveats) and `CARDINALITY_NOTE` (applied to all `/cardinality*` routes)
- **None of these scripts import the package** — they parse source with the stdlib `ast` module (except `generate_config_docs.py`, which does `importlib` a single isolated module, `core/config_models.py`, to introspect real Pydantic `FieldInfo` for types/defaults/constraints). This means renaming/moving classes or changing decorator names can silently break detection without raising an error — always check the printed "Found N ..." counts after running.
</critical_notes>

<file_map>
- `generate-docs.sh` - orchestrator; runs all 5 generators in a fixed order (config, **env-example**, metrics, collectors, endpoints) via `uv run python` (falls back to plain `python3` if `uv` isn't on PATH). This is what `make docgen` calls.
- `generate_config_docs.py` - loads `core/config_models.py` via `importlib` (isolated exec, not a package import) and walks the hardcoded `nested_models` list of Pydantic settings classes with `generate_model_docs()`, extracting field type/default/constraints (`ge`/`gt`/`le`/`lt`/`min_length`/`max_length`/`pattern`) into a table per section. Writes `docs/config.md`.
- `generate_env_example.py` - writes the repo-root **`.env.example`** from the config models. Unlike `generate_config_docs.py`'s hardcoded `nested_models` list, this one **auto-derives its sections by walking the top-level `Settings` model** (`core/config.py`) — every settable env var is emitted, commented at its default (required fields uncommented with an empty value), field description as a comment. It reuses `generate_config_docs.py`'s `find_repo_root`/`extract_constraints` (imported as a module). Because it walks the whole `Settings` tree, it cannot drift: adding a new `*Settings` model appears automatically (whereas `config.md` still needs a `nested_models` tuple added — keep the two in sync). `SECTION_TITLES` in the script only prettifies headers; a missing entry falls back to the upper-cased field name.
- `generate_metrics_docs.py` - AST-walks `src/` for `Gauge(...)`/`Counter(...)`/`Histogram(...)`/`Info(...)` instantiations (two visitor classes, `CreateMetricVisitor` and `PrometheusMetricVisitor`, cover two different construction patterns used in the codebase), resolves metric-name and label-name references back to the `*MetricName`/`LabelName` enum constants in `core/constants/*_constants.py` and `core/metrics.py`, categorizes by owning class, and writes a summary + per-collector tables to `docs/metrics/metrics.md`.
- `generate_collector_docs.py` - AST-walks `src/meraki_dashboard_exporter/collectors/` for class definitions, detects the `@register_collector` decorator to flag auto-registered "main" collectors vs. sub-collectors, resolves `UpdateTier.FAST/MEDIUM/SLOW` references, and groups unregistered sub-collectors by directory (`collectors/devices/`, `collectors/network_health_collectors/`, `collectors/organization_collectors/`). Writes `docs/collectors/reference.md`.
- `generate_endpoints_docs.py` - AST-walks for functions decorated with `@app.get/post/put/delete/patch/options/head(...)`, using the first line of the docstring as the description. Writes `docs/reference/endpoints.md`.
</file_map>

<paved_path>
## REGENERATE EVERYTHING
```bash
make docgen                # or: ./scripts/generate-docs.sh
```

## REGENERATE ONE DOC
```bash
make docs-config       # uv run python scripts/generate_config_docs.py
make docs-metrics      # uv run python scripts/generate_metrics_docs.py
make docs-collectors   # uv run python scripts/generate_collector_docs.py
make docs-endpoints    # uv run python scripts/generate_endpoints_docs.py
```

## ADDING A NEW SETTINGS SECTION TO config.md
1. Add the new `*Settings` model to `core/config_models.py` as usual.
2. Add a tuple to `nested_models` in `generate_config_docs.py`: `("Section Title", config_models.NewSettings, "MERAKI_EXPORTER_PREFIX", "One-line description")`.
3. Optionally add a freeform caveat to `section_notes` keyed by the same title.
4. Run `make docs-config` and check the diff.

## ADDING A CONDITIONAL/FEATURE-FLAGGED COLLECTOR, METRIC OWNER, OR ENDPOINT
Add an entry to the relevant hardcoded notes dict (`COLLECTOR_NOTES`, `CONDITIONAL_NOTES`, `ENDPOINT_NOTES`) so the generated docs surface the required env var — the generators have no way to infer this from code alone.
</paved_path>
