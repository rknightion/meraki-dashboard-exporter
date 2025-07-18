---
title: Configuration
description: Environment variables for the exporter
---

# Configuration

The exporter is configured entirely via environment variables. A sample `.env.example` file is provided and the [docker-compose.yml](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/docker-compose.yml) shows typical usage.

## Core settings
| Variable | Default | Description |
|----------|---------|-------------|
| `MERAKI_API_KEY` | *(none)* | API key from the Meraki Dashboard |
| `MERAKI_EXPORTER_ORG_ID` | *(all)* | Optional organisation ID to limit scope |
| `MERAKI_EXPORTER_LOG_LEVEL` | `INFO` | Logging level |
| `MERAKI_EXPORTER_PORT` | `9099` | Listening port |
| `MERAKI_EXPORTER_HOST` | `0.0.0.0` | Listening address |

## API settings
| Variable | Default | Description |
|----------|---------|-------------|
| `MERAKI_EXPORTER_API_BASE_URL` | `https://api.meraki.com/api/v1` | API endpoint (set regional URL if required) |
| `MERAKI_EXPORTER_API_TIMEOUT` | `30` | Timeout for API calls in seconds |
| `MERAKI_EXPORTER_API_MAX_RETRIES` | `4` | Retry attempts when requests fail |

## Update intervals
| Variable | Default | Description |
|----------|---------|-------------|
| `MERAKI_EXPORTER_FAST_UPDATE_INTERVAL` | `60` | Sensor metrics interval |
| `MERAKI_EXPORTER_MEDIUM_UPDATE_INTERVAL` | `300` | Device metrics interval |
| `MERAKI_EXPORTER_SLOW_UPDATE_INTERVAL` | `900` | Configuration metrics interval |

## OpenTelemetry
| Variable | Default | Description |
|----------|---------|-------------|
| `MERAKI_EXPORTER_OTEL_ENABLED` | `false` | Enable OTLP export |
| `MERAKI_EXPORTER_OTEL_ENDPOINT` | *(none)* | Collector endpoint |
| `MERAKI_EXPORTER_OTEL_SERVICE_NAME` | `meraki-dashboard-exporter` | OTEL service name |

For additional options see comments in `docker-compose.yml`.
Metric descriptions are available in the [Metrics Reference](metrics/metrics.md).
