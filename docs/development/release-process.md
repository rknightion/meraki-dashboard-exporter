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
4. **Docker images and the Helm chart are built, signed, and published** by
   `.github/workflows/publish.yml`, a reusable workflow that wraps the shared
   `rknightion/.github` `container-publish.yml` workflow. `release-please.yml`
   calls it two ways, gated by `release_created` so only one runs per push:
   - `release_created == true`: the `docker-release` job calls `publish.yml`
     with the new release tag, publishing the versioned image and Helm chart.
   - `release_created != true` (an ordinary push to `main`): the `edge` job
     calls `publish.yml` with no tag, publishing a `:main` edge image and a
     `0.0.0-main.*` snapshot Helm chart.

   Images go to `ghcr.io/<owner>/<repo>` with semver, branch, and PR tags; the
   chart is published to `ghcr.io/<owner>/charts/<chart-name>`. See
   [Security](../security.md) for how to verify image signatures.

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

`make check` is the local Python gate. It runs `ruff check`, `ruff format
--check`, mypy, and the test suite. Run it before committing Python or
documentation changes.

CI deliberately covers additional checks that are not part of `make check`:

- actionlint for workflow syntax and semantics;
- Helm lint plus a rendered-manifest kubeconform validation;
- Docker image build and startup smoke tests, including the non-root runtime
  assertion and HTTP endpoint checks;
- generated-documentation drift detection, offline API-model conformance, and
  the CI coverage threshold;
- zizmor, actionlint, and dependency review, which currently run outside the
  repository's required `ci-success` merge gate; and
- the separate CodeQL, Docker-security, and Scorecard workflows.

CI does not currently run `git diff --check`; use it locally when reviewing a
patch that may have whitespace errors. `make check` intentionally remains a
fast source-tree gate rather than a substitute for the container, chart, or
security workflow suites.
