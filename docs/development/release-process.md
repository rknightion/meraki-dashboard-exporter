---
title: Release Process
description: Release Meraki Dashboard Exporter with release-please, GitHub Actions, container images, and Helm chart publishing.
---

# Release Process

Releases are automated with **release-please** and GitHub Actions.

## How Releases Work

1. **release-please runs on pushes to `main`** (workflow:
   `.github/workflows/release-please.yml`) and opens/updates a release PR based
   on Conventional Commits.
2. The release PR updates:
   - `docs/changelog.md`
   - `pyproject.toml` (version bump)
   - `.release-please-manifest.json` (current released version)
3. **Merging the release PR** creates a Git tag (format `vX.Y.Z`) and GitHub
   Release.
4. **Docker images and the Helm chart are security-gated, built, signed, and published** by
   `.github/workflows/publish.yml`, a reusable workflow that wraps the shared
   `rknightion/.github` `container-publish.yml` workflow. `release-please.yml`
   calls it two ways, gated by `release_created` so only one runs per push:
   - `release_created == true`: the `docker-release` job calls `publish.yml`
     with the new release tag, publishing the versioned image and Helm chart.
   - `release_created != true` (an ordinary push to `main`): the `edge` job
     calls `publish.yml` with no tag, publishing a `:main` edge image and a
     `0.0.0-main.*` snapshot Helm chart.

   Before any image reaches GHCR, publication-scoped CodeQL rejects HIGH/CRITICAL findings, the
   committed Trivy exception file is validated, and each native OCI archive is scanned for
   HIGH/CRITICAL vulnerabilities that have an available fix. Only the exact scanned architecture digests proceed to manifest
   creation, signing, provenance, SBOM generation, and Helm publication.

   Images go to `ghcr.io/<owner>/<repo>` with semver, branch, and PR tags; the
   chart is published to `ghcr.io/<owner>/charts/<chart-name>`. See
   [Security](../security.md) for how to verify image signatures.

## Recovering a failed publish

A release can exist even when its image or chart publication fails. The release notes are marked
and the release is set to prerelease; check the workflow run as well, since the flagging job can
itself fail or be cancelled. First check whether the Docker Hub token has expired and renew it if
needed. Then inspect the failed publication job and correct its cause.

Use **Re-run failed jobs** on the Release Please run, never **Re-run all jobs**. Re-running all
jobs runs release-please again; it sees the existing release, skips the release publish, and runs
edge instead. If the run can no longer be rerun, dispatch the `publish` workflow with `release_tag`
set to the release tag. Both routes build the tag's tree: a fix to tagged code, such as the
Dockerfile or Trivy exceptions, needs a new patch release instead.

After verifying that both artefacts exist, remove the marked notice block from the release notes
and run `gh release edit <tag> --prerelease=false --latest`. A retry does not clear the flag or
notice automatically.

## Manual Trigger

You can also run the **Release Please** workflow manually from GitHub Actions (workflow_dispatch) to open or refresh the release PR.

## Notes

- The changelog used by release-please lives at `docs/changelog.md`.
- Configuration lives in `release-please-config.json`; the manifest with the
  current version is `.release-please-manifest.json`.
- Tags use `include-v-in-tag: true` (e.g. `v0.29.0`).
- Conventional Commit types `feat`, `fix`, `perf`, `refactor`, `deps`, and
  `docs` produce visible changelog sections; `chore`, `ci`, and `test` are
  hidden.
- Avoid manual version edits; use the release-please flow to keep tags and
  changelog consistent.

## Local and CI verification

`just check` is the local source-tree gate; its parts are the dependencies of the `check` recipe in
the `justfile`. The CI `test` job runs it and then `just groma-check`, which fails when a module
under `src/` is added or deleted without rescanning the architecture map. Run `just check` before
committing Python or documentation changes.

CI deliberately covers additional checks that are not part of `just check`:

- actionlint for workflow syntax and semantics;
- Helm lint plus a rendered-manifest kubeconform validation;
- Docker image build and startup smoke tests, including the non-root runtime
  assertion and HTTP endpoint checks;
- zizmor, actionlint, and dependency review, which are independently required by the `main`
  ruleset alongside `ci-success`; and
- the separate CodeQL, Docker-security, and Scorecard workflows.

Codecov and Codacy uploads are best-effort reporting. A provider outage does not replace or fail the
repository-owned 90% pytest line coverage floor enforced by `just check`.

CI does not currently run `git diff --check`; use it locally when reviewing a
patch that may have whitespace errors. `just check` intentionally remains a
source-tree gate rather than a substitute for the container, chart, or security
workflow suites. `just ci` adds the Docker-backed CI legs when Docker and
container-structure-test are available locally.
