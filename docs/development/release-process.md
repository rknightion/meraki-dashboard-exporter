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
4. **Docker images are built, signed, and published** when `release_created` is
   true: `release-please.yml` calls `docker-build.yml` via `workflow_call`,
   which also fires independently on pushes to `main` and on `v*` tag pushes.
   Images go to `ghcr.io/<owner>/<repo>` with semver, branch, and PR tags.

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
