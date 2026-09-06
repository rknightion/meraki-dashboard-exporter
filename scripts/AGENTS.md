# scripts/

The `generate_*.py` scripts read the source tree statically and overwrite committed documentation
and configuration artefacts. `just gen` runs them all; `docs/AGENTS.md` maps each artefact to its
generator. CI regenerates and diffs, so a stale artefact fails the build.

## What is derived and what is hand-maintained

Most of the output is derived, which makes the hand-maintained parts easy to miss. Each of these
needs a manual edit when you add the corresponding feature:

- `generate_config_docs.py` documents an **explicit list**, `get_nested_models()`, rather than
  walking the tree. It validates that list against the top-level `Settings` tree and **fails
  generation** if a section is missing, so add the
  `(title, config_models.NewSettings, "MERAKI_EXPORTER_PREFIX", description)` tuple with the model.
- The same file's `section_notes` dict holds freeform per-section caveats (for example the Network
  Filter include/exclude resolution rules). Nothing derives them.
- `generate_collector_docs.py` `COLLECTOR_NOTES`, `generate_metrics_docs.py`
  `EXCLUDED_CLASS_NAMES` / `CONDITIONAL_NOTES` / `INTERNAL_OWNERS`, and
  `generate_endpoints_docs.py` `ENDPOINT_NOTES` / `CARDINALITY_NOTE` are hardcoded exception dicts.
  A feature-flagged collector, an unwired metric class or a per-path caveat has to be added there;
  the generators cannot infer it from code.

## Analysis mode

None of these import the package. They parse with the stdlib `ast`, except `generate_config_docs.py`,
which `importlib`s the single module `core/config_models.py` in isolation to introspect real
Pydantic `FieldInfo` for types, defaults and constraints. `generate_env_example.py` and
`generate_helm_config.py` import `generate_config_docs.py` as a module to reuse its helpers.

A parse failure or an empty metric/collector scan fails generation rather than writing a truncated
artefact.

## generate_helm_config.py

- It splices into BEGIN/END marker regions in `charts/meraki-dashboard-exporter/values.yaml` and
  `templates/configmap.yaml`, and **errors when a marker is missing** rather than guessing where to
  write.
- **`SecretStr` fields are skipped entirely**: they must never land in a plaintext ConfigMap, and
  are injected through `extraEnv` from a Secret instead.
- `EXCLUDE` skips the three vars wired from higher-level chart values (`MERAKI__API_KEY`,
  `MERAKI__ORG_ID`, `SERVER__PORT`). Friendly key names are algorithmic camelCase with a small
  `NAME_OVERRIDES` map for legacy names. Set and frozenset defaults are sorted so output is
  deterministic.
- `tests/test_helm_config_drift.py` fails the build if the chart drifts from the schema or a secret
  leaks into the ConfigMap.

## The validators

- `validate_documented_env_vars.py` checks exact `MERAKI_EXPORTER_*` leaf variables in
  customer-facing README, docs and chart prose against the walked `Settings` tree. Generated config
  and changelog pages are excluded, and wildcard or model-prefix prose is not treated as a leaf.
- `validate_trivy_exceptions.py` is run by `.github/workflows/publish.yml`, not only by the gate.

`cloud-environment-setup.sh` is an end-user provisioner, deliberately not wired into a recipe
beyond a `bash -n` syntax check. Leave it that way.
