---
title: Getting Started
description: Install and run the exporter
---

# Getting Started

This section shows the quickest way to run the exporter.

## Requirements
- Docker
- Meraki Dashboard API access and key

## Setup

1. Copy `.env.example` to `.env` and set `MERAKI_API_KEY`.
2. Start the container with `docker compose up -d`. You can review the [docker-compose.yml](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml) for optional settings.

Alternatively, run directly with Docker:
```bash
docker run -d \
  -e MERAKI_EXPORTER_MERAKI__API_KEY=your_api_key_here \
  -p 9099:9099 \
  ghcr.io/rknightion/meraki-dashboard-exporter:latest
```

## Verify
- Visit `http://localhost:9099/metrics` to see metrics.
- `curl http://localhost:9099/health` should return `{"status": "healthy"}`.

Next read the [Configuration](config.md) guide for all settings and the
[Metrics Reference](metrics/metrics.md) for available metrics.
