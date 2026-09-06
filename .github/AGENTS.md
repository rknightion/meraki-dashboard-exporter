# .github/

Most security-scanner workflows here are thin callers of a shared reusable in the sibling
`rknightion/.github` repo rather than an inline job. The global GitHub Actions rule owns the
fleet-wide pinning and reusable-workflow behaviour; what follows is only what is specific to this
repo.

## Pinning

- Every third-party `uses:`, the `rknightion/.github` reusables included, is a full 40-character
  commit SHA with a trailing `# vX.Y.Z` comment. **Keep every `rknightion/.github` reference in this
  repo on the same version**; copy the pin from an existing caller rather than introducing a second,
  different one.
- Local same-repo references (`uses: ./.github/workflows/publish.yml`,
  `uses: ./.github/actions/report-drift`) are the only unpinned `uses:` and that is correct - they
  cannot be SHA-pinned.

## The required-check surface

- `ci.yml`'s `ci-success` is the aggregate required check: `if: always()` plus an explicit
  `contains(needs.*.result, 'failure'|'cancelled')` over `[test, docker-build-test,
  helm-lint-kubeconform]`. **A new job that should gate merges has to be added to that `needs:`
  list**, or it runs and blocks nothing.
- `scheduled-fleet-tests` and `on-demand-fleet-tests` are deliberately outside that list, so they
  never block a PR.
- The repository ruleset separately requires actionlint, zizmor and dependency review. When you add
  an independent scanner, update the ruleset only after observing the check's exact live name.

## harden-runner

Applied **per job, in `egress-policy: audit` mode**, not workflow-wide, and only on jobs that run
third-party steps. In `ci.yml` that is `test` and `docker-build-test`; its absence from the two
fleet-test jobs is deliberate. Audit mode logs egress without blocking, so it is not a hard
allowlist gate. A new job running third-party actions needs its own `harden-runner` step.

## Token minting

`release-please.yml`, `release-please-lock.yml` and `trigger-docs-sync.yml` each mint a per-run
GitHub App installation token from the OpenBao broker. **`id-token: write` has to be granted on the
minting job**; the workflow-level `permissions: {}` block does not cover it. Never swap a broker
step for `GITHUB_TOKEN` or a stored credential: the App identity is what keeps CI running
unattended on the release PR.

## Workflow-specific behaviour

- `release-please.yml` calls `publish.yml` twice, gated on `release_created` so the release build
  and the `:main` edge build never both fire on one push. On a release it prepends a limited-testing
  hardware-coverage warning to the release notes.
- `publish.yml` validates the expiring Trivy exception policy
  (`scripts/validate_trivy_exceptions.py`, `.trivyignore.yaml`) and runs publication-scoped
  HIGH-severity CodeQL before wrapping the shared `container-publish.yml`, passing
  `helm-chart-path: charts/meraki-dashboard-exporter` and `build-args: PY_VERSION=3.14`. Its
  `merge_group` trigger is a build-only arch-validation gate, no push.
- `api-drift.yml` fetches the live Meraki spec, runs `apidrift`, then `tufin/oasdiff breaking` over
  the reduced specs. `actions/report-drift` upserts a labelled tracking issue when the report
  fingerprint changes and then **always fails the job** - drift is a hard-fail signal once reported.
  `actions/resolve-drift` closes the issue when a lane comes back clean.
- `ci.yml`'s `docker-build-test` asserts the image runs as the non-root `exporter` user, so keep it
  aligned with the chart's security context.

**`issue-triage.yml` and `notify-new-issue.yml` were removed deliberately and are not part of this
repo.** Do not recreate them.
