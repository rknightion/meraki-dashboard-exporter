# OpenTelemetry Support

The Meraki Dashboard Exporter includes comprehensive OpenTelemetry (OTEL) support, automatically mirroring all Prometheus metrics to an OTEL collector.

## Overview

The exporter implements a **dual-export** strategy:
- **Primary**: Prometheus metrics exposed via `/metrics` endpoint
- **Secondary**: All Prometheus metrics are automatically mirrored to OTEL

This means every metric collected by the exporter is available in both Prometheus and OTEL formats without any additional configuration per metric.

## Configuration

OpenTelemetry export is disabled by default. To enable it, configure the following environment variables:

```bash
# Enable OTEL export
export MERAKI_EXPORTER_OTEL__ENABLED=true

# Set the OTEL collector endpoint
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://localhost:4317

# Optional: Configure service name (default: meraki-dashboard-exporter)
export MERAKI_EXPORTER_OTEL__SERVICE_NAME=my-meraki-exporter

# Optional: Set export interval in seconds (default: 60, range: 10-300)
export MERAKI_EXPORTER_OTEL__EXPORT_INTERVAL=30

# Optional: Add resource attributes (JSON format)
export MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES='{"environment":"production","region":"us-west"}'
```

## How It Works

### Automatic Metric Mirroring

The exporter uses a `PrometheusToOTelBridge` that:
1. Monitors the Prometheus registry for all registered metrics
2. Automatically creates corresponding OTEL metrics
3. Syncs metric values at the configured interval
4. Preserves all labels as OTEL attributes

### Metric Type Mapping

| Prometheus Type | OTEL Type | Notes |
|----------------|-----------|-------|
| Gauge | Gauge | Direct mapping |
| Counter | Counter | Tracks incremental changes |
| Histogram | Histogram | Records distribution |
| Info | Gauge | Special gauge with value=1 |

### Label to Attribute Conversion

All Prometheus labels are automatically converted to OTEL attributes with the same names and values.

## Example Configuration

### Docker Compose

```yaml
services:
  meraki-exporter:
    image: meraki-dashboard-exporter
    environment:
      - MERAKI_API_KEY=your_key
      - MERAKI_EXPORTER_OTEL__ENABLED=true
      - MERAKI_EXPORTER_OTEL__ENDPOINT=http://otel-collector:4317
      - MERAKI_EXPORTER_OTEL__EXPORT_INTERVAL=30
      - MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES={"service.namespace":"monitoring","deployment.environment":"prod"}
    ports:
      - "9099:9099"

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    volumes:
      - ./otel-config.yaml:/etc/otel-collector-config.yaml
    command: ["--config=/etc/otel-collector-config.yaml"]
```

### OTEL Collector Configuration

Example `otel-config.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:

exporters:
  # Send to Prometheus
  prometheus:
    endpoint: "0.0.0.0:8889"

  # Send to Jaeger for traces
  jaeger:
    endpoint: jaeger:14250
    tls:
      insecure: true

  # Send to a backend like Datadog, New Relic, etc.
  otlphttp:
    endpoint: https://your-backend.com/v1/metrics

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus, otlphttp]
```

## Monitoring OTEL Export

The exporter logs OTEL-related events:

```
INFO: Initialized Prometheus to OpenTelemetry bridge endpoint=http://localhost:4317 service_name=meraki-dashboard-exporter export_interval=60
INFO: Started OpenTelemetry metric export endpoint=http://localhost:4317 interval=60
DEBUG: Successfully synced metrics to OpenTelemetry metric_count=150
```

## Performance Considerations

- OTEL export runs in a separate async task
- Metric sync happens at the configured interval (default 60s)
- No impact on Prometheus metric collection or API calls
- Minimal memory overhead for tracking OTEL instruments

## Troubleshooting

### OTEL export not working

1. Check that `MERAKI_EXPORTER_OTEL__ENABLED=true` is set
2. Verify the endpoint is reachable: `telnet <host> <port>`
3. Check logs for connection errors
4. Ensure OTEL collector is configured to receive OTLP metrics

### Missing metrics in OTEL

1. Verify metrics appear in `/metrics` endpoint first
2. Check the export interval - metrics sync periodically
3. Look for warnings in logs about unsupported metric types
4. Ensure OTEL collector isn't dropping metrics

### High memory usage

If you have thousands of metrics with high cardinality:
1. Increase the export interval to reduce sync frequency
2. Consider filtering metrics at the OTEL collector level
3. Monitor the `metric_count` in debug logs

## Benefits

1. **No code changes required**: Adding new Prometheus metrics automatically adds OTEL metrics
2. **Unified monitoring**: Use the same metrics in both Prometheus and OTEL ecosystems
3. **Gradual migration**: Transition from Prometheus to OTEL at your own pace
4. **Correlation**: Correlate metrics with traces and logs in OTEL backends
5. **Flexibility**: Send metrics to multiple backends via OTEL collector

## Future Enhancements

- Metric filtering configuration
- Custom attribute enrichment
- Delta calculation optimization for counters
- Support for OTLP/HTTP protocol
- Metric metadata preservation
