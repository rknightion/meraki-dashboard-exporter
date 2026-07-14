# syntax=docker/dockerfile:1.25
ARG PY_VERSION=3.14

# --------------------------------------------------------------------------- #
# Builder stage - uses official slim image to compile wheels with uv
# --------------------------------------------------------------------------- #
# Digest-pinned for supply-chain immutability (#562). Renovate's built-in `dockerfile`
# manager natively tracks `FROM image:${ARG}@sha256:digest` (expands the ARG default to
# resolve the tag, then keeps the digest in sync with that tag) — no custom regex manager
# needed, unlike the UV_VERSION ARG below which lives outside a FROM line.
# Pinned digest resolves to python:3.14-slim-bookworm (3.14.6-slim-bookworm, multi-arch
# index incl. linux/amd64 + linux/arm64) as of 2026-07-02.
FROM python:${PY_VERSION}-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30 AS builder

# Install system deps with cache mounts for faster rebuilds
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libffi-dev \
        git \
        pkg-config

WORKDIR /app

# Configure uv for container builds
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Install uv for the target architecture
# renovate: datasource=github-releases depName=astral-sh/uv
ARG UV_VERSION=0.11.26
# Expected sha256 checksums for the uv release tarballs fetched below, one per supported
# TARGETARCH, pinned from https://github.com/astral-sh/uv/releases/download/<UV_VERSION>/sha256.sum
# (verified against that release's per-asset *.sha256 files too). This is a real pin — the
# values are committed here, not fetched at build time alongside the tarball they'd be
# checking, so a compromised/corrupted release download still fails the build (#562).
# Renovate's github-releases datasource only tracks UV_VERSION (comment above); it cannot
# compute these hashes, so whenever UV_VERSION bumps (via Renovate or by hand) these two
# ARGs must be refreshed in the same change — `make docker-uv-checksums` prints the current
# values for the pinned UV_VERSION to copy in. A stale checksum here fails the build loudly
# rather than silently installing an unverified uv, so this cannot go unnoticed.
ARG UV_CHECKSUM_AMD64=6426a73c3837e6e2483ee344cbc00f36394d179afcba6183cb77437e67db4af0
ARG UV_CHECKSUM_ARM64=befa1a59c91e96eb601b0fd9a97c03dd666f17baba644b2b4db9c59a767e387e
ARG TARGETARCH
RUN set -eux \
    && case "${TARGETARCH}" in \
         amd64) uv_arch="x86_64-unknown-linux-gnu"; uv_sha256="${UV_CHECKSUM_AMD64}" ;; \
         arm64) uv_arch="aarch64-unknown-linux-gnu"; uv_sha256="${UV_CHECKSUM_ARM64}" ;; \
         *) echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && if [ "${UV_VERSION}" = "latest" ]; then \
         echo "UV_VERSION=latest is a manual dev override only; it has no pinned checksum" >&2; \
         echo "and is intentionally not supported with checksum verification." >&2; \
         exit 1; \
       fi \
    && uv_url="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${uv_arch}.tar.gz" \
    && mkdir -p /tmp/uv \
    && curl -sSfL "${uv_url}" -o /tmp/uv.tar.gz \
    && echo "${uv_sha256}  /tmp/uv.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/uv.tar.gz -C /tmp/uv --strip-components=1 \
    && install -m 0755 /tmp/uv/uv /usr/local/bin/uv \
    && rm -rf /tmp/uv /tmp/uv.tar.gz \
    && uv --version

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
