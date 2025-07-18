---
title: Getting Started
description: Install and run the exporter
---

# Getting Started

This section shows the quickest way to run the exporter.

## Requirements
- Docker or Python 3.11+
- Meraki Dashboard API access and key

## Setup

1. Copy `.env.example` to `.env` and set `MERAKI_API_KEY`.
2. Start the container with `docker compose up -d`. You can review the [docker-compose.yml](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml) for optional settings.

Alternatively install with Python:
```bash
uv pip install meraki-dashboard-exporter
export MERAKI_API_KEY=your_key
python -m meraki_dashboard_exporter
```

## Verify
- Visit `http://localhost:9099/metrics` to see metrics.
- `curl http://localhost:9099/health` should return `{"status": "healthy"}`.

Next read the [Configuration](config.md) guide for all settings and the
[Metrics Reference](metrics/metrics.md) for available metrics.
