# Meraki Dashboard Exporter

<div align="center">
  <h1>Meraki Dashboard Exporter</h1>

  **A Prometheus exporter for Cisco Meraki Dashboard API metrics with OpenTelemetry support**

  [![GitHub Release](https://img.shields.io/github/v/release/rknightion/meraki-dashboard-exporter?style=flat-square)](https://github.com/rknightion/meraki-dashboard-exporter/releases)
  [![Docker Pulls](https://img.shields.io/docker/pulls/ghcr.io/rknightion/meraki-dashboard-exporter?style=flat-square)](https://github.com/rknightion/meraki-dashboard-exporter/pkgs/container/meraki-dashboard-exporter)
  [![License](https://img.shields.io/github/license/rknightion/meraki-dashboard-exporter?style=flat-square)](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/LICENSE)
</div>

## Overview

The Meraki Dashboard Exporter is a high-performance Prometheus exporter that collects metrics from the Cisco Meraki Dashboard API. It provides comprehensive monitoring capabilities for your Meraki infrastructure, supporting all device types and organization-level metrics.

## Key Features

<div class="grid cards" markdown>

- :material-speedometer: **High Performance**
  Asynchronous collection with intelligent tiering for optimal API usage

- :material-chart-line: **Comprehensive Metrics**
  Support for all Meraki device types (MS, MR, MV, MT, MX, MG)

- :material-docker: **Container Ready**
  Production-ready Docker images with health checks

- :material-cloud-sync: **OpenTelemetry**
  Built-in support for metrics and structured logging

- :material-gauge: **Smart Collection**
  Three-tier update system matching Meraki API data freshness

- :material-shield-check: **Enterprise Ready**
  Structured logging, error handling, and performance monitoring

</div>

## Quick Start

=== "Docker"

    ```bash
    # Create configuration
    cat > .env << EOF
    MERAKI_API_KEY=your_api_key_here
    MERAKI_EXPORTER_LOG_LEVEL=INFO
    EOF

    # Run with Docker
    docker run -d \
      --name meraki-exporter \
      --env-file .env \
      -p 9099:9099 \
      ghcr.io/rknightion/meraki-dashboard-exporter:latest
    ```

=== "Docker Compose"

    ```yaml
    services:
      meraki-exporter:
        image: ghcr.io/rknightion/meraki-dashboard-exporter:latest
        ports:
          - "9099:9099"
        environment:
          - MERAKI_API_KEY=${MERAKI_API_KEY}
        restart: unless-stopped
    ```

=== "Python"

    ```bash
    # Install with uv
    uv pip install meraki-dashboard-exporter

    # Set environment
    export MERAKI_API_KEY=your_api_key_here

    # Run exporter
    python -m meraki_dashboard_exporter
    ```

## Architecture

```mermaid
graph LR
    A[Meraki Dashboard API] -->|HTTPS| B[Meraki Exporter]
    B --> C[Prometheus Metrics]
    B --> D[OpenTelemetry]
    C --> E[Prometheus Server]
    D --> F[OTLP Collector]
    E --> G[Grafana]

    style B fill:#00a0a0,stroke:#008080,color:#fff
    style A fill:#78BE20,stroke:#5a8f16,color:#fff
```

## Metrics at a Glance

| Category | Examples | Update Frequency |
|----------|----------|------------------|
| **Organization** | API usage, licenses, device counts, client counts | 5 minutes |
| **Devices** | Status, uptime, performance | 5 minutes |
| **Sensors** | Temperature, humidity, door status, water detection | 60 seconds |
| **Alerts** | Active alerts by severity and type | 5 minutes |
| **Configuration** | Security settings, change tracking | 15 minutes |

## Next Steps

<div class="grid cards" markdown>

- :material-rocket-launch: **[Getting Started](getting-started/quickstart.md)**
  Get up and running in minutes

- :material-book-open-variant: **[Metrics Reference](metrics/overview.md)**
  Detailed documentation of all metrics

- :material-wrench: **[Operations Guide](operations/deployment.md)**
  Production deployment best practices

- :material-puzzle: **[Integration Guide](integration/prometheus.md)**
  Connect with Prometheus and Grafana

</div>

## Support

- **Issues**: [GitHub Issues](https://github.com/rknightion/meraki-dashboard-exporter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/rknightion/meraki-dashboard-exporter/discussions)
- **Security**: See [SECURITY.md](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/SECURITY.md)
