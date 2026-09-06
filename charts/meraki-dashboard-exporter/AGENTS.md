# charts/meraki-dashboard-exporter/

Helm chart for the exporter. The in-repo `version` is static and the publish workflow overrides it
with the release tag at package time, so neither it nor `appVersion` is a fact to rely on. The
chart is published alongside the container image by `.github/workflows/publish.yml`
(`helm-chart-path: charts/meraki-dashboard-exporter`).

Render locally with a dummy key, because a render with neither key value set fails on purpose:

    helm template test-release charts/meraki-dashboard-exporter --set meraki.apiKey=dummy
    helm lint charts/meraki-dashboard-exporter

## API key

- `values.yaml` defaults both `meraki.apiKey` and `meraki.existingSecret` to `""`. **There is no
  insecure default**, and `_validation.tpl`'s `validateApiKey` `fail`s the render unless exactly one
  of the two is set. Both set, or neither, is a hard fail by design; do not relax it, and never
  default `apiKey` to a placeholder.
- `validateApiKey` is invoked once, with the shutdown-grace and OTel validators, at the top of
  `deployment.yaml`. That covers `helm install/upgrade`, which renders every template, but a
  `--show-only` render of another template alone skips it. Do not add a second call site and do not
  remove the existing one.
- `deployment.yaml` always builds the API-key `secretKeyRef` from the `secretName` / `secretKey`
  helpers, which resolve for both branches precisely because `validateApiKey` has already
  guaranteed exactly one is set. **Do not reintroduce an `if .Values.meraki.existingSecret` branch
  around that env var** - that shape leaves the chart-managed-Secret path with no API-key env var
  at all. On that path `secretKey` returns `MERAKI_EXPORTER_MERAKI__API_KEY`, matching the key
  `secret.yaml` writes into `stringData`.
- Prefer `existingSecret` for real deployments: the chart-managed Secret's value lands in release
  history.

## Config plumbing

Config is entirely env-var driven, never a mounted file. `templates/configmap.yaml` maps `config.*`
keys to `MERAKI_EXPORTER_<SECTION>__<KEY>`; the double underscore is the nested-Pydantic-Settings
delimiter from `core/config.py`.

- **The `config:` knobs are generated, not hand-maintained.** Both the `config: {}` block in
  `values.yaml` and the mapping in `configmap.yaml` sit between
  `# >>> BEGIN generated config knobs ... >>>` / `# <<< END ... <<<` markers written by
  `scripts/generate_helm_config.py`. Add the field to the Pydantic `Settings` model and run
  `just gen`; both sides appear together. Editing inside the markers is lost at the next run, and
  `tests/test_helm_config_drift.py` fails the build if the chart drifts from the schema.
- Every knob is `hasKey`-guarded inside `{{- with .Values.config }}`, so an all-default `config`
  emits nothing and the app falls back to its own defaults.
- **Hand-wired specials live outside the markers**: `MERAKI_EXPORTER_MERAKI__ORG_ID` (from
  `meraki.organizationId`) and `MERAKI_EXPORTER_SERVER__PORT` (from `service.port`).
- **Secret-typed settings are excluded from the ConfigMap entirely.**
  `MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET` and `MERAKI_EXPORTER_SERVER__API_TOKEN` are injected
  through `extraEnv` from a Secret, never templated into plaintext.
- `extraEnv` may not override the two chart-owned validated settings, `SERVER__PORT` and
  `API__PER_FETCH_DEADLINE_SECONDS`; `_validation.tpl` fails the render if it does. Use
  `service.port` so listener, Service and probes stay aligned, and
  `config.apiPerFetchDeadlineSeconds` so `terminationGracePeriodSeconds` is validated against it.
- `checksum/config` and `checksum/secret` annotations in `deployment.yaml` hash the *rendered*
  templates. `secret.yaml` renders to an empty string on the `existingSecret` path, so that
  checksum is inert there rather than broken.

## Singleton

The exporter has no leader election, so `deployment.yaml` hard-`fail`s the render when
`replicaCount > 1` or `autoscaling.maxReplicas > 1`: two pods double the per-org Meraki API load and
emit duplicate metrics. `strategy.type: Recreate` stops two pods overlapping during a rollout, and
when `autoscaling.enabled` the Deployment omits its static `replicas` so the HPA owns it, capped at
1. Do not relax these guards or switch to `RollingUpdate` without adding leader election first.

## Runtime posture

- Pod and container `securityContext` both set `runAsNonRoot: true`, uid and gid 1000,
  `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false` and drop all capabilities. The
  ServiceAccount sets `automountServiceAccountToken: false`, and a 64Mi `/tmp` `emptyDir` exists to
  satisfy the read-only root filesystem. CI asserts the image itself runs non-root, so keep the two
  consistent.
- `readinessProbe` is `/ready` and `livenessProbe` is `/health`. **`/health` always returns 200**,
  so pointing readiness back at it silently turns the gate into a no-op.
- The default 100m/256Mi request and 500m/512Mi limit are a bootable default, not a supported scale
  tier. Memory scales with device and network cardinality; size from the evidence labels in the
  `resources:` block and `docs/scaling-guide.md`, and do not reintroduce tier recommendations.
- Meraki delivers webhooks to `POST /api/webhooks/meraki` over **HTTPS only** and the exporter
  serves plain HTTP, so the optional Ingress or an external proxy is the TLS-termination point.
- `serviceMonitor.enabled`, `ingress.enabled`, `networkPolicy.enabled` and `autoscaling.enabled` all
  default `false` and each guards its own template. `networkPolicy` egress covers DNS, 443 and the
  shared OTLP port; a channel on a distinct port needs `networkPolicy.egress.extraEgress`.
- `README.md` here is hand-written, not generated. Keep it in step with `values.yaml` yourself.
