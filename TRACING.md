# OpenTelemetry Tracing Support

The Meraki Dashboard Exporter includes comprehensive OpenTelemetry tracing support to help you understand request flow, identify bottlenecks, and debug issues.

## Overview

Tracing is automatically enabled when OpenTelemetry is configured. It provides:
- Distributed tracing for all API calls
- Automatic instrumentation of HTTP requests (via the Meraki SDK)
- FastAPI request tracing
- Threading instrumentation for async operations
- Log correlation with trace IDs
- Configurable sampling rates
- **Automatic RED metrics generation from trace spans**

## Configuration

Tracing is enabled automatically when OTEL is configured:

```bash
# Required: Enable OTEL and set endpoint
export MERAKI_EXPORTER_OTEL__ENABLED=true
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://localhost:4317

# Optional: Configure sampling rate (default: 10%)
export MERAKI_EXPORTER_OTEL__SAMPLING_RATE=0.1  # Sample 10% of traces

# Optional: Set service name (default: meraki-dashboard-exporter)
export MERAKI_EXPORTER_OTEL__SERVICE_NAME=my-meraki-exporter
```

## Sampling Strategies

The exporter uses tail-based sampling with parent-based decisions:

- **Root spans**: Sampled based on the configured rate (default 10%)
- **Child spans**: Always included if parent is sampled
- **Remote traces**: Respect upstream sampling decisions

Sampling rates:
- `0.0`: No traces (effectively disabled)
- `0.1`: 10% of traces (default, recommended for production)
- `0.5`: 50% of traces (good for debugging)
- `1.0`: All traces (development/debugging only)

## Instrumented Components

### 1. HTTP Requests (Meraki SDK)
All Meraki API calls are automatically traced:
- Request/response timing
- HTTP status codes
- Rate limit headers
- Request IDs
- Response sizes

### 2. FastAPI Application
- Endpoint execution time
- Request/response details
- Exception tracking
- Excludes `/health` and `/metrics` endpoints

### 3. Threading
- `asyncio.to_thread()` operations
- Thread pool executor tasks
- Concurrent API calls

### 4. Logging
- Automatic trace ID injection
- Log correlation across services
- Structured logging with trace context

## Trace Attributes

### Common Attributes
- `service.name`: Service identifier
- `service.version`: Exporter version
- `deployment.environment`: Environment (from resource attributes)

### HTTP Attributes
- `http.method`: GET, POST, etc.
- `http.url`: Full request URL
- `http.status_code`: Response status
- `http.response.size`: Response body size

### Meraki-Specific Attributes
- `meraki.request_id`: Meraki request tracking ID
- `meraki.retry_after`: Rate limit retry delay
- `meraki.rate_limit.remaining`: Remaining API calls
- `api.endpoint`: Meraki API endpoint name
- `org.id`: Organization ID (when applicable)
- `network.id`: Network ID (when applicable)

### Custom Spans
- `get_organizations`: Fetching organizations
- `collect_metrics`: Metric collection cycles
- `api_call`: Individual API operations

## Example OTEL Collector Configuration

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:
    timeout: 1s
    send_batch_size: 1024

  # Tail sampling for production
  tail_sampling:
    decision_wait: 10s
    num_traces: 100
    expected_new_traces_per_sec: 10
    policies:
      - name: errors-policy
        type: status_code
        status_code: {status_code: ERROR}
      - name: slow-traces-policy
        type: latency
        latency: {threshold_ms: 1000}
      - name: probabilistic-policy
        type: probabilistic
        probabilistic: {sampling_percentage: 10}

exporters:
  # Send to Jaeger
  jaeger:
    endpoint: jaeger:14250
    tls:
      insecure: true

  # Send to backend
  otlphttp:
    endpoint: https://your-backend.com/v1/traces

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch, tail_sampling]
      exporters: [jaeger, otlphttp]
```

## Viewing Traces

### Jaeger UI
```bash
# Run Jaeger locally
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 14250:14250 \
  jaegertracing/all-in-one:latest

# Access UI at http://localhost:16686
```

### Grafana Tempo
Integrate with Grafana for visualization:
1. Add Tempo data source
2. Configure OTLP endpoint
3. Use TraceQL for queries

### Example Queries

**Find slow API calls:**
```traceql
{service.name="meraki-dashboard-exporter" && duration > 1s}
```

**Find failed requests:**
```traceql
{service.name="meraki-dashboard-exporter" && status.code=ERROR}
```

**Track specific organization:**
```traceql
{service.name="meraki-dashboard-exporter" && org.id="123456"}
```

## Performance Considerations

### Overhead
- Tracing adds ~1-2% CPU overhead
- Memory usage increases by ~10-20MB
- Network bandwidth for trace export

### Best Practices
1. Use sampling in production (10% recommended)
2. Increase sampling when debugging
3. Use tail sampling to capture errors
4. Set appropriate export intervals
5. Monitor trace export errors

### Optimization Tips
- Batch trace exports
- Use async export
- Configure appropriate queue sizes
- Set reasonable timeouts

## Troubleshooting

### No traces appearing
1. Verify OTEL is enabled: `MERAKI_EXPORTER_OTEL__ENABLED=true`
2. Check endpoint connectivity
3. Verify sampling rate > 0
4. Check exporter logs for errors

### Missing spans
1. Ensure parent spans are sampled
2. Check instrumentation is loaded
3. Verify no exceptions in span creation

### High memory usage
1. Reduce sampling rate
2. Decrease export batch size
3. Lower span queue size

### Export failures
1. Check network connectivity
2. Verify collector is running
3. Check for authentication issues
4. Monitor queue overflow

## Integration Examples

### With Datadog
```bash
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://datadog-agent:4317
export MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES='{"env":"production","service":"meraki-exporter"}'
```

### With New Relic
```bash
export MERAKI_EXPORTER_OTEL__ENDPOINT=https://otlp.nr-data.net:4317
export MERAKI_EXPORTER_OTEL__HEADERS='{"api-key":"YOUR_NR_LICENSE_KEY"}'
```

### With AWS X-Ray
```bash
export MERAKI_EXPORTER_OTEL__ENDPOINT=http://aws-otel-collector:4317
export MERAKI_EXPORTER_OTEL__RESOURCE_ATTRIBUTES='{"aws.region":"us-east-1"}'
```

## Span Metrics (RED Metrics)

The exporter automatically generates RED (Rate, Errors, Duration) metrics from trace spans:

### Generated Metrics
- **`meraki_span_requests_total`**: Total requests by operation, collector, endpoint, and status
- **`meraki_span_duration_seconds`**: Request duration histogram with configurable buckets
- **`meraki_span_errors_total`**: Error counts by operation and error type

### Benefits
- No manual instrumentation required
- Automatic SLI/SLO calculation
- Consistent metrics across all operations
- Lower cardinality than raw traces
- Perfect for dashboards and alerting

### Example Queries
```promql
# Request rate by collector
rate(meraki_span_requests_total[5m])

# Error rate percentage
sum(rate(meraki_span_errors_total[5m])) by (collector)
/
sum(rate(meraki_span_requests_total[5m])) by (collector)
* 100

# P99 latency by operation
histogram_quantile(0.99,
  sum(rate(meraki_span_duration_seconds_bucket[5m])) by (operation, le)
)
```

## Correlation with Metrics

Traces can be correlated with Prometheus metrics:
1. Use trace ID in log messages
2. Add trace ID as metric label (sparingly)
3. Use exemplars for metric-trace correlation
4. Query both in Grafana dashboards
5. RED metrics provide automatic correlation between traces and metrics

## Future Enhancements

- Baggage propagation for request context
- Custom span attributes from config
- Trace-based alerting rules
- Advanced sampling strategies
- Span metrics generation
