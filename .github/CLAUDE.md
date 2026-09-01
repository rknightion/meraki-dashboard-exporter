<system_context>
CI/CD for the repo: 16 workflows + 2 composite actions implementing an elaborate but consistent
security/release pipeline — release automation, container + Helm chart publishing, three
independent security scanners (CodeQL, zizmor, docker-security), dependency-review,
OSSF Scorecard, and a scheduled Meraki-API-drift lane. Most security-scanner workflows are thin
wrappers that `uses:` a **shared reusable workflow** from the sibling `rknightion/.github` repo
rather than defining the job inline. The removed issue-automation workflows
`issue-triage.yml` and `notify-new-issue.yml` are not part of this repository; don't recreate them
from memory of an earlier version of this doc.
</system_context>

<critical_notes>
- **Action-pinning policy (strict, repo-wide): every third-party `uses:` — including the shared
  `rknightion/.github/.github/workflows/*.yml` reusables — is pinned to a full 40-char commit SHA
  with a trailing `# vX.Y.Z` comment**, e.g.
  `uses: rknightion/.github/.github/workflows/zizmor.yml@ff43f62eaec9f41d49b9a208d86b2eb932c97056 # v1.18.1`.
  Never pin to a mutable tag/branch (`@v1`, `@main`). `renovate.json` has a `github-actions`
  manager package rule (`rebaseWhen: conflicted`) so Renovate is what bumps these SHAs — a new
  workflow should follow the same SHA+comment style so Renovate can track it. Local same-repo
  references (`uses: ./.github/workflows/publish.yml`, `uses: ./.github/actions/report-drift`)
  are the only unpinned `uses:` and that's correct/expected — they can't be SHA-pinned.
  Verified current shared-reusable ref: `ff43f62eaec9f41d49b9a208d86b2eb932c97056 # v1.18.1`
  (git log shows this gets bumped repo-wide in one commit when rknightion/.github cuts a release —
  keep all `rknightion/.github` refs in this repo on the *same* pinned version).
- **Release-please mints a short-lived GitHub App installation token per run through the OpenBao
  broker** (`release-please.yml`) — the job exchanges its OIDC identity for a token scoped to this
  repository. The App-authored release PR keeps CI (including the `rknightion/.github` reusable
  workflows, which pull code from another repo) running unattended. Keep the broker-token step and
  its `id-token: write` permission; do not replace it with a stored credential or the default
  workflow token.
- **`harden-runner` (step-security) is applied per-job, in `egress-policy: audit` mode** — it is
  NOT blanket-applied to every job in a workflow, only to specific jobs that run
  untrusted/third-party steps. In `ci.yml` it's on `test` and `docker-build-test` but deliberately
  absent from `slow-tests` (schedule-only, not part of the `ci-success` required-check surface); it
  is also present in `api-drift.yml` and `release-please-lock.yml` (and, for Scorecard, inside the shared `rknightion/.github` reusable rather than the local wrapper). Audit mode logs egress
  without blocking — it is not currently a hard allowlist gate. When adding a new job that runs
  third-party actions, add `harden-runner` to that job specifically, don't assume workflow-level
  coverage.
- **`ci.yml`'s `ci-success` job is the aggregate required status check**
  (`if: always()` + explicit `contains(needs.*.result, 'failure'|'cancelled')` check over
  `[test, docker-build-test, helm-lint-kubeconform]`). `slow-tests` (schedule-only) is deliberately
  NOT in that `needs` list so it doesn't block PRs. The ruleset separately requires actionlint,
  zizmor, and dependency review. When adding an aggregate CI job, add it to `ci-success`'s `needs:`;
  when adding an independent scanner, update the ruleset after observing its exact live check name.
- **`trigger-docs-sync.yml`** fires a `repository_dispatch` to a *different* repo
  (`m7kni/m7kni-net-site`) on `docs/**`/`docs.toml`/`scripts/**` changes. It authenticates with a
  short-lived GitHub App installation token minted per run through the OpenBao broker, scoped to
  the documentation hub's contents write permission; the workflow default token is not sufficient
  for this cross-repository dispatch.
</critical_notes>

<file_map>
## Workflows (`.github/workflows/`)
- `ci.yml` - main gate: mypy, offline apidrift conformance check, pytest (`--cov-fail-under=80`,
  best-effort reporting to Codecov + Codacy), a Docker build+startup smoke test (asserts non-root `exporter`
  user), a schedule-only `slow-tests` job, and the `ci-success` required-check aggregator.
- `release-please.yml` - cuts releases using the per-run OpenBao broker token described above; on
  `release_created`, prepends a "limited testing" hardware-coverage warning to the GitHub release notes, then calls
  `publish.yml` (release build). On non-release pushes to `main`, calls `publish.yml` again for an
  `:main` edge build + edge Helm chart. `release_created` gates the two `publish.yml` calls so they
  never both fire on one push. Uses `release-please-config.json` / `.release-please-manifest.json`.
- `publish.yml` - reusable (`workflow_call` + `workflow_dispatch` + `merge_group`); validates the
  expiring Trivy exception policy, runs publication-scoped HIGH-severity CodeQL, then wraps the shared
  `rknightion/.github` pre-push Trivy `container-publish.yml` reusable, passing
  `helm-chart-path: charts/meraki-dashboard-exporter` (chart is published alongside the image) and
  `build-args: PY_VERSION=3.14`. The `merge_group` trigger is a build-only (no push) arch-validation
  gate on the merge queue.
- `api-drift.yml` - daily (06:17 UTC) + manual; see `tools/apidrift/CLAUDE.md` for the tool itself.
  Fetches the live Meraki spec over HTTPS, runs `apidrift`, then `tufin/oasdiff breaking` on the
  reduced specs; opens/closes a tracking issue via the two composite actions below.
- `codeql.yml` / `zizmor.yml` / `actionlint.yml` / `dependency-review.yml` / `docker-security.yml` -
  thin wrappers around `rknightion/.github` shared reusables (see pinning note above); each grants
  only the specific `permissions:` its job needs, workflow-level `permissions: {}`.
- `scorecard.yml` - OSSF Scorecard, thin wrapper around the `rknightion/.github` shared
  `scorecard.yml` reusable (v1.4.0+; `push` + weekly `schedule`). Uploads SARIF to code scanning
  and publishes to the OpenSSF API for the scorecard.dev badge. No PAT (fleet uses Rulesets).
- `release-please-lock.yml` - regenerates `uv.lock` on the release-please PR and pushes it with a
  per-run OpenBao broker GitHub App token so `uv sync --locked` passes on the release PR; idempotent.
- `trigger-docs-sync.yml` - cross-repo `repository_dispatch` on changes to `docs/**`, `docs.toml`,
  or `scripts/**`.
- `arm-automerge.yml` / `auto-rc.yml` - thin callers for release-PR auto-merge arming and
  exact-CI-head release-candidate creation/publication.
- `ghcr-cleanup.yml` - weekly shared-workflow caller for image/chart retention, plus manual dry-run.
- `failure-harness.yml` - manual, redacted fault-injection replay against the retained harness
  corpus; builds a local image and uploads artifacts even when the selected replay fails closed.

## Composite actions (`.github/actions/`)
- `report-drift/action.yml` - deterministically upserts a labelled tracking issue from a Markdown
  report when its fingerprint changes, then always fails the job (drift is a hard-fail signal once
  reported).
- `resolve-drift/action.yml` - closes any open tracking issue(s) for a given `lane-label` when a
  scheduled lane comes back clean.
</file_map>

<paved_path>
## Adding a new workflow
1. Pin every third-party `uses:` to a full commit SHA + `# vX.Y.Z` comment (match existing style
   exactly so Renovate's `github-actions` manager picks it up).
2. Set workflow-level `permissions: {}` and grant narrower `permissions:` per job.
3. If it should block merges, add its job name to `ci.yml`'s `ci-success` `needs:` list.
4. If it wraps `rknightion/.github`, use the same pinned SHA as the other shared-reusable
   workflows in this repo (currently `ff43f62eaec9f41d49b9a208d86b2eb932c97056 # v1.18.1`) —
   don't introduce a second, different pin.
</paved_path>

<fatal_implications>
- **NEVER replace the broker-minted release token with `GITHUB_TOKEN` or a stored credential** —
  that breaks unattended CI on the release PR.
- **NEVER pin a new third-party action to a mutable tag/branch** — full SHA + version comment only.
- **NEVER let a new required CI job go unadded to `ci-success`'s `needs:`** — it silently won't gate.
</fatal_implications>
