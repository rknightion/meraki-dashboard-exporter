# apidrift

Standalone CLI living under `tools/`, not part of the `meraki_dashboard_exporter` package. It
compares the vendored OpenAPI baseline against the live upstream spec, scoped to the operations this
exporter actually consumes, and checks the exporter's Pydantic models against live response schemas.

- Invoke it as `PYTHONPATH=src:tools uv run python -m apidrift ...`: `apidrift` has to resolve from
  `tools/` while still importing `meraki_dashboard_exporter` for `models.conformance_models()`.
- **Exit codes are load-bearing and CI branches on them:** `0` clean or INFO-only, `2` usage or IO
  error, `3` actionable drift (BREAKING or WARNING). Do not repurpose them.
- `--suggest` and `--coverage` are review aids and always exit 0. `--coverage` is offline, fetches
  no spec, and has no `just` recipe - run it directly.

## Recipes and CI

- `just api-conformance` runs `--conformance-only` with the vendored baseline as both `--baseline`
  and `--live`, so it never needs network. It is in `just check` and is what CI runs per PR.
- `just api-drift` runs the full check against the live spec URL.
- `just refresh-spec` re-vendors `spec/meraki-openapi.json.gz` and prints the new `info.version`;
  hand-update the version note in `spec/README.md` afterwards. Never hand-edit the gzip.
- `.github/workflows/api-drift.yml` (daily cron plus dispatch) runs the full check with
  `--emit-reduced`, then `tufin/oasdiff breaking` over the reduced baseline/live pair with
  `spec/oasdiff-ignore.txt`. Drift upserts a tracking issue through `.github/actions/report-drift`;
  a clean run closes it through `.github/actions/resolve-drift`.

## Decisions that look like bugs

- `spec/apidrift-ignore.txt` (`--ignore`) is the narrow acknowledge lever: case-insensitive
  substring match against a finding's `kind|op|detail`, and a match is **downgraded to
  `INFO <kind>-acknowledged`, never dropped** - an accepted risk that vanishes from the report is an
  accepted risk nobody remembers. Prefer it to `just refresh-spec`, which silences everything,
  including drift nobody has reviewed.
- The tracking issue's body is current state; a comment means it changed. `report-drift`
  fingerprints the report into `<!-- drift-fingerprint: sha256 -->` in the body and does nothing at
  all when the fingerprint matches. Any change to the report's rendering churns the fingerprint and
  produces one "changed" comment.
- Severities are deliberately asymmetric. `model-extra` (a model field absent from every mapped op's
  response) is only INFO, because the exporter's models legitimately carry derived and enrichment
  fields; only `type-mismatch` and `model-op-absent` are WARNING, and only WARNING and BREAKING gate.
- **`INFO spec-untyped` means the spec describes no fields, not that the model is stale.** Some ops
  declare a free-form `{"type": "object"}` response; `model-extra` cannot be asserted against an
  undescribed response, so a model with any untyped mapped op reports one `spec-untyped` finding and
  has its `model-extra` findings suppressed. Do not "fix" it by deleting model fields.
- Deprecation is checked over the consumed operation set, not the mapped models
  (`check_deprecated_operations`), because `conformance_models()` collects only models defined in
  `core/api_models.py` and `core/domain_models.py` and would miss one that lives in a collector
  module. Deprecated in both specs is `INFO op-deprecated`, non-gating on purpose so a years-old
  deprecation cannot pin the tracking issue open; deprecated in live only is
  `WARNING op-newly-deprecated`, and re-vendoring the baseline is its acknowledge path. Ops absent
  from the live spec are skipped: `BREAKING missing-op` already covers removal, and the consumed set
  carries scanner false positives that are not operations at all.

## Model annotations

- Mapping is opt-in and declared on the model: `__meraki_op__` (str or `list[str]`, own attribute,
  never inherited) or `__meraki_derived__ = True`. An unannotated model is reported `INFO unmapped`
  rather than skipped, so the coverage gap stays visible. `--suggest` scores candidate ops by
  field-name overlap.
- A nested structural submodel that only ever appears as a field of a parent whose response the
  parent already maps carries `__meraki_derived__ = True`, **not** the parent's `__meraki_op__`. Its
  fields are not top-level fields of any op response, so mapping it to the parent op emits false
  `model-extra` findings; oasdiff catches its drift through the reduced parent schema.
- `__meraki_beta__ = True` declares that a mapped op lives on the beta channel. apidrift pulls a
  single GA spec, so beta-tagged ops are absent from it entirely and their drift is out of scope;
  the flag turns a false `WARNING model-op-absent` into a visible, non-gating `INFO
  beta-blind-spot`. Nothing sets it yet - it exists so the first beta-dependent collector surfaces
  the blind spot instead of a false positive. Fetching a beta channel is unimplemented.

## Untrusted input

- `--live-url` is parsed with `urlparse`, requires `scheme == "https"` and a non-empty `hostname`,
  and the URL that reaches `urlopen` is rebuilt from the parsed components. A
  `startswith("https://")` prefix check does not stop scheme smuggling and was flagged as CWE-918.
  Never hand the raw argument to `urlopen`, here or anywhere else in this tool.
- Fetched spec content and the rendered report are external data. `report-drift` passes the report
  to `gh issue` as a value, never as executable content.

## Adding a consumed operation

Call it from a collector, annotate any new backing model with `__meraki_op__` or
`__meraki_derived__`, and run `just api-conformance`. If the call uses an SDK controller that is not
already in `scanner.py`'s `MERAKI_CONTROLLERS` frozenset, add it: the scanner AST-matches
`<receiver>.<controller>.<method>`, so an unknown controller is a silent false negative, not a crash.
