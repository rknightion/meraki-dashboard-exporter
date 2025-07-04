# Build stage
FROM python:3.13-slim AS builder

# Set environment variables for build
# PYTHONDONTWRITEBYTECODE: Prevents .pyc files during install
# PYTHONUNBUFFERED: Ensures build output is visible
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install uv
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml .
COPY README.md .

# Install dependencies
RUN uv pip install --system --no-cache .

# Runtime stage
FROM python:3.13-slim

# Create non-root user
RUN useradd -m -u 1000 exporter

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/meraki_dashboard_exporter /app/meraki_dashboard_exporter

# Switch to non-root user
USER exporter

# Expose metrics port
EXPOSE 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:9090/health').raise_for_status()"

# Run the exporter
CMD ["python", "-m", "meraki_dashboard_exporter"]