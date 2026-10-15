# Loop: meraki-dashboard-exporter
tier: guarded
gate: just check
ci-required: actionlint / Run actionlint, ci-success, dependency-review / Dependency review, zizmor / Run zizmor
release-on-push: yes
deploy-on-push: no
grafana-stack: none

Public repository: no email, handle, org or account ID, device serial, MAC, host name or credential
value in any tracked file, `backlog/` included. Run `just` with stdin from `/dev/null`.

## Credentials

- A Meraki API key sits in the gitignored `.env` for live-API verification. Never log, echo or
  widen an error path that could carry it.
- `[confirm]` recipes push a multi-arch image to ghcr.io or prune the machine-wide buildx cache:
  stop, never pass `--yes` or `JUST_YES=1`.

## Traps

- `just check` is CI's `test` job only. A change to the `Dockerfile`, entrypoint or image runtime
  shape is gated by `docker-build-test`: run `just ci` (`image-verify` requires `Config.User` to be
  `exporter`; `image-structure` needs `container-structure-test` or its container equivalent;
  `smoke` needs `/health` and `/metrics` to return 200). A green `just check` means nothing there.
- The publish Trivy gate runs only in `publish.yml` and fails on any HIGH or CRITICAL not accepted
  in `.trivyignore.yaml`. A release can exist with no artifact behind it, and exceptions silently
  stop applying when the base image's distro changes.
- Generated artifacts are committed and overwritten silently: run `just gen` when metrics, config,
  endpoints, collectors, the settings schema or the chart config change.
- The vendored OpenAPI spec is wrong for some endpoints: verify response shapes against the live API.
- Never add a client-keyed or otherwise unbounded labelled Prometheus metric; per-client signals go
  to the data-log emitter.
- Every network fetch goes through `OrganizationInventory.get_networks(org_id)`, the one enforcement
  point for the configured `NetworkFilter`. The only bypasses are `DiscoveryService` and the two
  inventory-unavailable `_fetch_networks_direct` fallbacks, which reapply the filter by hand; add no
  other. Reach the API only through the instrumented facade (AIMD is the sole pacer).
- No raw `asyncio.gather` in a collector: use `ManagedTaskGroup` or `process_in_batches_with_errors`.
  Metric and label names come from the enums in `core/constants/metrics_constants.py` and `LabelName`;
  emit through `parent._set_metric()`; wrap new fetchers in `validate_response_format`.
- Model every Meraki field as optional (nulls arrive), and treat a 404/402 on a license-gated endpoint
  as "not licensed", never a failure streak.
- A metric or label rename is not done until `grafana/dashboards/*.json` and `grafana/alerts/` are
  updated and checked against a live scrape: an orphaned panel renders "No data" and nothing fails.
- Never hand-edit a generated artefact; `generate_helm_config.py` skips `SecretStr` fields on purpose.
- An in-repo `CLAUDE.md` is a claim to verify against the tree, not ground truth.
- A `Closes #N` or `Fixes #N` trailer on a commit pushed to `main` auto-closes a contributor's
  GitHub issue. Cite the number in prose.

## Mutexes

- Single-owner files, serialised: `core/metrics.py`, `core/constants/metrics_constants.py`,
  `core/collector.py`, `core/metric_expiration.py`, `core/config_models.py` (`.env.example`,
  `docs/config.md` and the Helm knob blocks are generated from it), `collectors/manager.py`,
  `collectors/device.py`, `collectors/organization.py`, `collectors/network_health.py` and `app.py`.
  A new enum goes into its seam first.
- The live Meraki organisation (read-only GETs only, its rate-limit budget shared), the soak host
  (read-only, root only, named only in ignored local config) and the Grafana stack: root only, one
  at a time.
- A push to `main` redeploys the soak host (watchtower on `:main`), which resets its counters:
  snapshot or pin a digest before relying on them.
- `rknightion/.github`: read-only unless the owner grants authority.
