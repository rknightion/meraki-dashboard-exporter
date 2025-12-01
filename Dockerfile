# syntax=docker/dockerfile:1.20
ARG PY_VERSION=3.14

# --------------------------------------------------------------------------- #
# Builder stage - uses official slim image to compile wheels with uv
# --------------------------------------------------------------------------- #
FROM python:${PY_VERSION}-slim-bookworm AS builder

# Install system deps with cache mounts for faster rebuilds
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libffi-dev \
        pkg-config

WORKDIR /app

# Configure uv for container builds
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Install uv for the target architecture
ARG UV_VERSION=latest
ARG TARGETARCH
ARG TARGETVARIANT
RUN set -eux \
    && case "${TARGETARCH}${TARGETVARIANT:-}" in \
         amd64) uv_arch="x86_64-unknown-linux-gnu" ;; \
         arm64) uv_arch="aarch64-unknown-linux-gnu" ;; \
         armv7) uv_arch="armv7-unknown-linux-gnueabihf" ;; \
         *) echo "Unsupported TARGETARCH=${TARGETARCH}${TARGETVARIANT:-}" >&2; exit 1 ;; \
       esac \
    && if [ "${UV_VERSION}" = "latest" ]; then \
         uv_url="https://github.com/astral-sh/uv/releases/latest/download/uv-${uv_arch}.tar.gz"; \
       else \
         uv_url="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${uv_arch}.tar.gz"; \
       fi \
    && mkdir -p /tmp/uv \
    && curl -sSfL "${uv_url}" -o /tmp/uv.tar.gz \
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
FROM python:${PY_VERSION}-slim-bookworm AS runtime

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

# Environment setup - use the venv Python
# Note: PYTHONDONTWRITEBYTECODE removed since we pre-compile bytecode
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

# Switch to non-root user
USER exporter

# Expose metrics port
EXPOSE 9099

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import httpx; httpx.get('http://localhost:9099/health').raise_for_status()"]

# Use ENTRYPOINT for the main command
ENTRYPOINT ["python", "docker-entrypoint.py"]
