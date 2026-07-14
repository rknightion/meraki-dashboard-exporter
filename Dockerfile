# syntax=docker/dockerfile:1.25
ARG PY_VERSION=3.14

# --------------------------------------------------------------------------- #
# Builder stage - uses official slim image to compile wheels with uv
# --------------------------------------------------------------------------- #
# Digest-pinned for supply-chain immutability (#562). Renovate's built-in `dockerfile`
# manager natively tracks `FROM image:${ARG}@sha256:digest` (expands the ARG default to
# resolve the tag, then keeps the digest in sync with that tag) — no custom regex manager
# needed. The uv `COPY --from` pin below rides on the same built-in manager (#661).
# Pinned digest resolves to python:3.14-slim-bookworm (3.14.6-slim-bookworm, multi-arch
# index incl. linux/amd64 + linux/arm64) as of 2026-07-02.
FROM python:${PY_VERSION}-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30 AS builder

# Install system deps with cache mounts for faster rebuilds
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        libffi-dev \
        git \
        pkg-config

WORKDIR /app

# Configure uv for container builds
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Install uv from its official image, digest-pinned for supply-chain immutability (#562, #661).
# The @sha256 digest is an immutable content address for the whole image, committed here rather
# than fetched at build time alongside the artefact it would be verifying — the same guarantee the
# python base pins above rely on. Renovate's built-in `dockerfile` manager natively tracks
# `COPY --from` refs and updates the tag and digest together in one commit, so uv bumps land
# unattended. (The previous curl+tarball+sha256sum approach could not: Renovate bumped the version
# ARG but had no way to compute the tarball hashes, so every bump broke the build.)
# The image is a multi-arch index (linux/amd64 + linux/arm64), so no TARGETARCH handling is needed.
COPY --from=ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa /uv /uvx /bin/

# Copy dependency files first (most cacheable layer)
COPY pyproject.toml uv.lock ./

# Create virtual environment and install dependencies with cache mount
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-install-project

# Copy application source code directly (not as a package)
COPY src/meraki_dashboard_exporter ./meraki_dashboard_exporter

# --------------------------------------------------------------------------- #
# Runtime stage - minimal Debian-based Python image
# --------------------------------------------------------------------------- #
# Same digest pin as the builder stage above (#562) — both stages must resolve to the
# identical base image.
FROM python:${PY_VERSION}-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30 AS runtime

# Install runtime dependencies and create non-root user
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 -s /bin/false exporter

# Labels for container metadata (consolidated for single layer)
LABEL org.opencontainers.image.source="https://github.com/rknightion/meraki-dashboard-exporter" \
      org.opencontainers.image.description="Prometheus exporter for Cisco Meraki Dashboard API metrics" \
      org.opencontainers.image.vendor="Rob Knight" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Copy the virtual environment from builder (with pre-compiled bytecode)
COPY --link --from=builder --chown=1000:1000 /app/.venv /app/.venv

# Copy application code from builder
COPY --link --from=builder --chown=1000:1000 /app/meraki_dashboard_exporter ./meraki_dashboard_exporter

# Copy entrypoint script
COPY --link --chown=1000:1000 docker-entrypoint.py ./

# Bake the build-time version into the image (F-118). The repo pyproject.toml is
# not present in the runtime stage and deps are installed with
# `uv sync --no-install-project`, so both of get_version()'s local sources miss;
# MERAKI_EXPORTER_VERSION is the runtime fallback surfaced in /status, the web UI,
# and the OTel service.version resource attribute. Passed via
# `--build-arg APP_VERSION=<version>` (see CI wiring); defaults to the dev sentinel.
ARG APP_VERSION=0.0.0+dev

# Bake the build-time git commit SHA into the image for meraki_exporter_build_info
# (MET-10). Passed via `--build-arg GIT_COMMIT=<sha>` (CI passes `github.sha`);
# defaults to `unknown` for local builds without the build-arg (DEP-06).
ARG GIT_COMMIT=unknown

# Environment setup - use the venv Python
# Note: PYTHONDONTWRITEBYTECODE removed since we pre-compile bytecode
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    MERAKI_EXPORTER_VERSION=${APP_VERSION} \
    MERAKI_EXPORTER_COMMIT=${GIT_COMMIT}

# Switch to non-root user
USER exporter

# Expose metrics port
EXPOSE 9099

# Health check. Reads the configurable server port from the same env var the
# app itself uses (MERAKI_EXPORTER_SERVER__PORT, default 9099) so overriding
# the port at `docker run` time doesn't leave the baked-in check probing the
# wrong port.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import os, httpx; port = os.environ.get('MERAKI_EXPORTER_SERVER__PORT', '9099'); httpx.get(f'http://localhost:{port}/health').raise_for_status()"]

# Use ENTRYPOINT for the main command
ENTRYPOINT ["python", "docker-entrypoint.py"]
