# Release Process

This document describes the release process for the Meraki Dashboard Exporter.

## Version Management

The project follows [Semantic Versioning](https://semver.org/):
- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality additions
- **PATCH** version for backwards-compatible bug fixes

The version is maintained in `pyproject.toml` as the single source of truth.

## Automated Release Process

The Makefile provides automated commands for creating releases:

### Quick Release Commands

```bash
# Create a patch release (0.0.X)
make release-patch

# Create a minor release (0.X.0)
make release-minor

# Create a major release (X.0.0)
make release-major
```

### What These Commands Do

1. **Pre-release checks**: Runs `make check` (lint, typecheck, tests)
2. **Update dependencies**: Runs `uv lock` to ensure lock file is current
3. **Bump version**: Updates version in `pyproject.toml`
4. **Commit changes**: Commits version bump and updated lock file
5. **Create git tag**: Tags the commit with `v{version}`
6. **Push to GitHub**: Pushes commits and tags (with confirmation)
7. **Create GitHub release**: Uses `gh` CLI to create release with auto-generated notes

### Manual Version Control

```bash
# Show current version
make version

# Manually set a specific version
make version-set NEW_VERSION=1.2.3

# Bump versions without releasing
make version-bump-patch
make version-bump-minor
make version-bump-major
```

## GitHub Actions Automation

Once a release is created, GitHub Actions automatically:

1. **Publishes to PyPI** (`python-publish.yml`)
   - Triggers on release creation
   - Builds and uploads Python package to PyPI

2. **Builds Docker images** (`docker-build.yml`)
   - Triggers on version tags (`v*`)
   - Builds multi-architecture images
   - Pushes to Docker Hub and GitHub Container Registry

## Manual Release Process

If you prefer manual control:

1. Update version in `pyproject.toml`
2. Run `uv lock` to update lock file
3. Commit changes: `git commit -am "chore: bump version to X.Y.Z"`
4. Create tag: `git tag -a vX.Y.Z -m "Release version X.Y.Z"`
5. Push: `git push origin main --tags`
6. Create GitHub release manually or with:
   ```bash
   gh release create vX.Y.Z --generate-notes
   ```

## Pre-release Checklist

Before releasing:
- [ ] All tests pass (`make test`)
- [ ] Code is linted (`make lint`)
- [ ] Type checking passes (`make typecheck`)
- [ ] CHANGELOG is updated (if maintaining one)
- [ ] Documentation is up to date

## Troubleshooting

### Version Already Exists on PyPI
If PyPI rejects the upload due to version conflict:
1. Bump the version again
2. Ensure you're not re-using a previously published version

### GitHub CLI Not Found
Install GitHub CLI:
```bash
# macOS
brew install gh

# Linux
# See: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
```

### Push Permission Denied
Ensure you have push access to the repository and your Git credentials are configured.

## Version Information at Runtime

The application dynamically reads its version from `pyproject.toml` via the `__version__.py` module. This ensures version consistency across:
- FastAPI app info endpoint (`/`)
- API documentation
- Logs and metrics
