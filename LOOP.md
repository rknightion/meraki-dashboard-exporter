# Loop: meraki-dashboard-exporter
tier: guarded
gate: just check
ci-required: actionlint / Run actionlint, ci-success, dependency-review / Dependency review, zizmor / Run zizmor
release-on-push: yes
deploy-on-push: no
receiver: https://loopwatch.m7kni.com
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
- A `Closes #N` or `Fixes #N` trailer on a commit pushed to `main` auto-closes a contributor's
  GitHub issue. Cite the number in prose.

## Mutexes

None recorded.
