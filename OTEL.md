# OpenTelemetry Support

The Meraki Dashboard Exporter includes comprehensive OpenTelemetry (OTEL) support for both metrics and distributed tracing.

## Overview

The exporter provides:
- **Metrics**: All Prometheus metrics are automatically mirrored to OTEL
- **Tracing**: Distributed tracing for all API calls and operations
- **Logging**: Correlated logs with trace context

### Dual-Export Strategy
- **Primary**: Prometheus metrics exposed via `/metrics` endpoint
- **Secondary**: All metrics and traces sent to OTEL collector

This means every metric collected by the exporter is available in both Prometheus and OTEL formats, plus you get full observability with distributed tracing.

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

## Distributed Tracing

When OTEL is enabled, the exporter automatically provides distributed tracing:

### Automatic Instrumentation
- **HTTP Requests**: All Meraki API calls via requests library
- **FastAPI**: All HTTP endpoints (except /health and /metrics)
- **Threading**: asyncio.to_thread operations
- **Logging**: Automatic trace ID injection

### Configuration
```bash
# Set sampling rate (default: 10%)
export MERAKI_EXPORTER_OTEL__SAMPLING_RATE=0.1
```

### Trace Attributes
- Meraki request IDs
- Rate limit information
- Organization and network IDs
- API endpoint names
- Response sizes and status codes

See [TRACING.md](TRACING.md) for detailed tracing documentation.

## Log Correlation

When OTEL is enabled, all structured logs automatically include trace context:

### Features
- **Automatic Trace Correlation**: Every log entry includes trace_id and span_id when within a trace context
- **Structured Field Preservation**: All structured log fields are preserved in logfmt format
- **Context Propagation**: Trace context flows through all log entries
- **Easy Integration**: Works with any log aggregation system that can parse structured logs

### Log Attributes
Each log entry includes:
- `trace_id`, `span_id`, `trace_flags` - When within a trace context
- `timestamp` - ISO format timestamp
- `level` - Log severity level
- `event` - Log message
- All custom fields added via structured logging

### Example Log Output
```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "info",
  "event": "Collected metrics successfully",
  "trace_id": "a1b2c3d4e5f6789012345678901234567",
  "span_id": "1234567890123456",
  "collector": "DeviceCollector",
  "duration": "2.34s",
  "device_count": 150
}
```

### Benefits
- **Unified Telemetry**: Metrics, traces, and logs in one platform
- **Correlation**: Easy to find logs for a specific trace or span
- **Filtering**: Use trace context to filter relevant logs
- **Debugging**: Full context for troubleshooting issues

## Benefits

1. **No code changes required**: Adding new Prometheus metrics automatically adds OTEL metrics
2. **Full observability**: Metrics, traces, and logs in one platform
3. **Unified monitoring**: Use the same data in both Prometheus and OTEL ecosystems
4. **Gradual migration**: Transition from Prometheus to OTEL at your own pace
5. **Root cause analysis**: Correlate metrics with traces to debug issues
6. **Flexibility**: Send telemetry to multiple backends via OTEL collector

## Future Enhancements

- Metric filtering configuration
- Custom attribute enrichment
- Delta calculation optimization for counters
- Support for OTLP/HTTP protocol
- Metric metadata preservation
- Baggage propagation for request context
