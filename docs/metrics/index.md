---
title: Metrics Reference
description: Complete reference for all metrics collected by the Meraki Dashboard Exporter
tags:
  - prometheus
  - monitoring
  - metrics
---

# Metrics Reference

The Meraki Dashboard Exporter provides comprehensive metrics for monitoring your Cisco Meraki infrastructure. This section contains detailed documentation about all available metrics, their collection tiers, and usage examples.

## Documentation Structure

<div class="grid cards" markdown>

- :material-chart-line-stacked: **[Metrics Overview](overview.md)**

    ---

    High-level overview of metric categories, collection tiers, and naming conventions

- :material-format-list-bulleted-square: **[Complete Reference](metrics.md)**

    ---

    Detailed reference of every metric with descriptions, labels, and examples

</div>

## Metric Categories

### Organization Metrics
- License usage and expiration
- API usage statistics
- Overall device and client counts
- Bandwidth utilization

### Device Metrics
- Device status and uptime
- Performance indicators
- Configuration state

### Network Health Metrics
- Wireless connection statistics
- Channel utilization
- RF health indicators

### Environmental Metrics (MT Sensors)
- Temperature readings
- Humidity levels
- Door and motion sensors
- Water detection

### Alert Metrics
- Active alerts by severity
- Alert counts by type
- Security events

## Collection Tiers

The exporter uses a three-tier collection system:

| Tier | Interval | Metrics | Purpose |
|------|----------|---------|---------|
| **Fast** | 60 seconds | Environmental sensors | Real-time monitoring |
| **Medium** | 5 minutes | Device status, network health | Operational monitoring |
| **Slow** | 15 minutes | Configuration, licenses | Change detection |

## Getting Started

1. **Browse the Overview**: Start with the [overview](overview.md) to understand the metric structure
2. **Find Specific Metrics**: Use the [complete reference](metrics.md) to find detailed information
3. **Use in Queries**: See examples in our [Integration & Dashboards](../integration-dashboards.md) guide

## Prometheus Query Examples

```promql
# Device availability by organization
avg by (org_name) (meraki_device_up) * 100

# Top networks by client count
topk(5, sum by (network_name) (meraki_mr_clients_connected))

# Temperature sensors above threshold
meraki_mt_temperature_celsius > 30
```

!!! tip "Performance Tips"
    - Use recording rules for frequently accessed metrics
    - Filter by organization or network early in queries
    - Consider metric cardinality when using high-cardinality labels
