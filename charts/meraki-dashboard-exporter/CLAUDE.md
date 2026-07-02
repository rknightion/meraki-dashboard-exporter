<system_context>
Helm chart for deploying the exporter to Kubernetes. `apiVersion: v2`, `type: application`,
chart `version: 0.1.0` (bumped independently of `appVersion`, which tracks the exporter release —
currently `0.28.0`). Published via the shared `container-publish.yml` reusable workflow
(`.github/workflows/publish.yml`, `helm-chart-path: charts/meraki-dashboard-exporter`) alongside the
container image — the chart is a recent addition (started publishing per the
"start publishing Helm chart" commit).
</system_context>

<critical_notes>
- **API key handling is validated at render time, not defaulted.** `values.yaml` defaults
  `meraki.apiKey` and `meraki.existingSecret` to `""` — there is **no insecure default value**.
  `templates/_validation.tpl`'s `validateApiKey` template `fail`s the render unless **exactly one**
  of `meraki.apiKey` / `meraki.existingSecret` is set. It is invoked from a single call site at the
  top of `templates/deployment.yaml` (line 1) — that is sufficient because `helm install/upgrade`
  renders every template in the release, but a `--show-only` render of a different template alone
  would skip it. Don't add a second call site; don't remove the existing one.
- **FIXED (was a confirmed bug) — the chart-managed-Secret path now wires the key into the
  container.** `deployment.yaml`'s `env:` block used to only add the `MERAKI_EXPORTER_MERAKI__API_KEY`
  var when `.Values.meraki.existingSecret` was set, leaving the `meraki.apiKey` (chart-managed
  Secret) path with no env var at all. It now unconditionally builds the `secretKeyRef` from
  `_helpers.tpl`'s `secretName`/`secretKey` helpers, which resolve correctly for both branches
  because `validateApiKey` (see above) guarantees exactly one of `apiKey`/`existingSecret` is set
  by the time this block renders. Also fixed `secretKey`'s non-`existingSecret` default, which
  incorrectly returned the literal string `"api-key"` — it now returns
  `"MERAKI_EXPORTER_MERAKI__API_KEY"`, matching the actual key name `secret.yaml` writes into
  `stringData`. Verified with `helm template --set meraki.apiKey=dummy` and
  `--set meraki.existingSecret=my-secret` (both now render the env var correctly) and
  `--set meraki.apiKey=... --set meraki.existingSecret=...` / neither set (both still hard-`fail`
  via `validateApiKey`, unchanged). If you touch this area again, keep using the helpers rather
  than reintroducing an `if .Values.meraki.existingSecret` branch in `deployment.yaml` — that's
  exactly the shape that caused the original bug.
  - Both `apiKey` and `existingSecret` set, or neither set, is a hard `fail` at render time (see
    `validateApiKey` above) — that part is intentional, not a bug to relax.
- **Config is entirely env-var driven**, not a mounted file: `templates/configmap.yaml` maps every
  `values.yaml` `config.*` / `service.port` / `meraki.organizationId` key to a
  `MERAKI_EXPORTER_<SECTION>__<KEY>` env var (double-underscore = nested Pydantic Settings
  delimiter — matches `src/meraki_dashboard_exporter/core/config.py`'s `Settings`). Adding a new
  configurable setting means adding a `values.yaml` key **and** a corresponding line in
  `configmap.yaml` (or `deployment.yaml`'s env block for secrets) — the two are not auto-synced.
- **Pod restart on config/secret change** is via `checksum/config` + `checksum/secret` annotations
  in `deployment.yaml`, computed by hashing the *rendered* configmap.yaml/secret.yaml templates —
  standard Helm pattern, but note `secret.yaml` renders to an empty string when
  `meraki.existingSecret` is used (its own `if` guard), so that checksum is stable/inert on that path.
- **Security posture is hardened by default and worth preserving as-is**: pod + container
  `securityContext` both set `runAsNonRoot: true` / non-root uid+gid 1000,
  `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, all capabilities dropped; the
  ServiceAccount sets `automountServiceAccountToken: false`; a writable `/tmp` `emptyDir` (`64Mi`) is
  mounted explicitly to satisfy the read-only root FS. `ci.yml`'s `docker-build-test` job actually
  asserts the image runs as a non-root `exporter` user — keep chart and image defaults consistent.
- **`serviceMonitor.enabled` defaults to `false`** (Prometheus Operator CRD may not be installed) —
  it's the one optional resource; everything else always renders.
</critical_notes>

<file_map>
- `Chart.yaml` - chart metadata (name, `version`, `appVersion`, maintainers, keywords).
- `values.yaml` - all configurable values, extensively commented with `# --` (helm-docs style)
  annotations per key; the source of truth for defaults — read this before changing a template.
- `.helmignore` - standard VCS/editor-artifact excludes, nothing project-specific.
- `templates/_helpers.tpl` - naming helpers (`name`, `fullname`, `chart`, `labels`,
  `selectorLabels`, `serviceAccountName`) plus the API-key `secretName`/`secretKey` resolvers.
- `templates/_validation.tpl` - `validateApiKey`: fails the render on a misconfigured API key (see
  above). The only validation template in the chart.
- `templates/deployment.yaml` - the Deployment; single call site for `validateApiKey`; wires
  ConfigMap via `envFrom`, conditionally wires `existingSecret` via `secretKeyRef`, checksum
  annotations, probes, resources, the `/tmp` emptyDir.
- `templates/configmap.yaml` - env-var mapping for all non-secret settings (see above).
- `templates/secret.yaml` - chart-managed API key Secret; only renders when `meraki.apiKey` is set.
- `templates/service.yaml` - ClusterIP (by default) Service exposing the `http` port.
- `templates/serviceaccount.yaml` - optional ServiceAccount (`serviceAccount.create`), token
  automount disabled.
- `templates/servicemonitor.yaml` - optional Prometheus Operator `ServiceMonitor` (guarded by
  `serviceMonitor.enabled`).
- `templates/NOTES.txt` - post-install help text (port-forward + curl examples, warns if no API
  key is configured). Readiness hint is `/ready`, matching the chart's default
  `readinessProbe.httpGet.path` (also `/ready` as of `8639c1b` / #243 — `/health` is always `200`,
  which made the readiness gate a no-op, so don't point `readinessProbe` back at it; `livenessProbe`
  is the one that stays on `/health`). Still worth cross-checking `values.yaml` if this file looks
  like it's drifted, but the two agree today.
</file_map>

<paved_path>
## Local render / lint
```bash
helm template test-release charts/meraki-dashboard-exporter --set meraki.apiKey=dummy
helm lint charts/meraki-dashboard-exporter
```
(the chart intentionally fails to render with neither `meraki.apiKey` nor `meraki.existingSecret`
set — that's the validation working, not a broken default).

## Adding a new `config.*` setting
1. Add the key (with a `# --` doc comment) to `values.yaml` under `config:`.
2. Add the matching `MERAKI_EXPORTER_<SECTION>__<KEY>` line to `templates/configmap.yaml`.
3. Confirm the env var name matches the nested Pydantic `Settings` model in
   `src/meraki_dashboard_exporter/core/config.py` / `config_models.py`.
</paved_path>

<fatal_implications>
- **NEVER default `meraki.apiKey` to a non-empty placeholder** in `values.yaml` — the empty-string
  default plus the `validateApiKey` fail-fast is the intended safety net against silently deploying
  with a checked-in dummy key.
- **NEVER remove/relax the `validateApiKey` fail** to allow both or neither of apiKey/existingSecret.
- **NEVER wire the chart-managed Secret's value through anywhere that could land it in `helm get
  values`/release history unnecessarily** beyond the existing `stringData` field — prefer
  `existingSecret` for real deployments.
</fatal_implications>
