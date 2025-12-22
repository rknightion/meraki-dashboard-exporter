# Release Process

Releases are automated with **release-please** and GitHub Actions.

## How Releases Work

1. **release-please runs on pushes to `main`** and opens/updates a release PR.
2. The release PR updates:
   - `docs/changelog.md`
   - `pyproject.toml` (version bump)
3. **Merging the release PR** creates a Git tag and GitHub Release.
4. **Docker images are built, signed, and published** via the `docker-build` workflow.

## Manual Trigger

You can also run the **Release Please** workflow manually from GitHub Actions (workflow_dispatch) to open or refresh the release PR.

## Notes

- The changelog used by release-please lives at `docs/changelog.md`.
- Avoid manual version edits; use the release-please flow to keep tags and changelog consistent.
