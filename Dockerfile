# syntax=docker/dockerfile:1.17
ARG PY_VERSION=3.13

# --------------------------------------------------------------------------- #
# Builder stage - uses official slim image to compile wheels with uv
# --------------------------------------------------------------------------- #
FROM --platform=${BUILDPLATFORM} python:${PY_VERSION}-slim-bookworm AS builder

# System deps needed for building wheels
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

# Download the latest installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin/:$PATH"

# Verify uv is installed
RUN uv --version

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock README.md ./

# Create virtual environment and install dependencies using uv
# uv will create .venv in the current directory
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --frozen --no-install-project

# Copy application source code
COPY src ./src

# Install the project itself (without deps, as they're already installed)
RUN uv sync --frozen --no-dev

# --------------------------------------------------------------------------- #
# Runtime stage - minimal Debian-based Python image
# --------------------------------------------------------------------------- #
FROM python:${PY_VERSION}-slim-bookworm AS runtime

# Install runtime dependencies and create non-root user
RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 -s /bin/false exporter

# Labels for container metadata
LABEL org.opencontainers.image.source="https://github.com/rknightion/meraki-dashboard-exporter"
LABEL org.opencontainers.image.description="Prometheus exporter for Cisco Meraki Dashboard API metrics"
LABEL org.opencontainers.image.vendor="Rob Knight"
LABEL org.opencontainers.image.licenses="MIT"

# Copy the virtual environment from builder
COPY --from=builder --chown=exporter:exporter /app/.venv /app/.venv

# Environment setup - use the venv Python
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app"

WORKDIR /app

# Copy application code from builder
COPY --from=builder --chown=exporter:exporter /app/src/meraki_dashboard_exporter ./meraki_dashboard_exporter

# Switch to non-root user
USER exporter

# Expose metrics port
EXPOSE 9099

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import httpx; httpx.get('http://localhost:9099/health').raise_for_status()"]

# Use ENTRYPOINT for the main command
ENTRYPOINT ["python", "-m", "meraki_dashboard_exporter"]
