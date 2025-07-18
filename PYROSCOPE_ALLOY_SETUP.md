# Pyroscope Alloy Configuration for Meraki Dashboard Exporter

This document explains the Alloy configurations for scraping profiling data from the Meraki Dashboard Exporter and sending it to Grafana Cloud.

## Overview

The Meraki Dashboard Exporter provides comprehensive profiling endpoints that are compatible with pprof tooling. These configurations enable continuous profiling with Grafana Cloud Pyroscope.

## Available Configurations

### 1. Standard Configuration (`alloy-pyroscope-config.alloy`)

**Use Case**: General production monitoring with balanced resource usage.

**Key Features**:
- 30-second scrape interval
- Covers all profiling endpoints
- Balanced approach for continuous monitoring
- Good for baseline performance analysis

**Profile Types Captured**:
- **CPU Profile** (`profile`): Duration-based, 29s windows
- **Wall Clock Profile** (`wall`): Duration-based, 29s sampling
- **Heap Profile** (`heap`): Memory allocation snapshots
- **Allocations Profile** (`allocs`): Memory allocation tracking
- **Goroutine Profile** (`goroutine`): Thread and async task info
- **Block Profile** (`block`): Blocking operations analysis
- **Mutex Profile** (`mutex`): Lock contention analysis
- **In-Use Objects** (`inuse_objects`): Python object counts by type
- **In-Use Space** (`inuse_space`): Memory usage by allocation site
- **Exceptions** (`exceptions`): Python exception tracking

### 2. High-Frequency Configuration (`alloy-pyroscope-high-frequency.alloy`)

**Use Case**: Capturing burst activity during collection cycles.

**Key Features**:
- Dual scraper approach: 15s for critical profiles, 60s for background
- Optimized for the "once a minute, over in seconds" activity pattern
- Higher resolution capture during burst periods
- Separate job labels for filtering

**Benefits**:
- Captures short-lived CPU/memory spikes during data collection
- Reduces noise in background profiles
- Better resource utilization

## Setup Instructions

### 1. Enable Profiling on the Exporter

Ensure profiling is enabled:

```bash
export MERAKI_EXPORTER_ENABLE_PROFILING=true
```

Or in your `.env` file:
```
MERAKI_EXPORTER_ENABLE_PROFILING=true
```

### 2. Verify Endpoints are Available

Check that profiling endpoints are responding:

```bash
# Health check
curl http://localhost:9099/health

# Verify profiling is enabled
curl http://localhost:9099/debug/pprof/heap | head -5
```

Should return profile data, not "Profiling is disabled" message.

### 3. Configure Alloy

Choose the appropriate configuration:

```bash
# For standard monitoring
alloy run alloy-pyroscope-config.alloy

# For high-frequency burst capture
alloy run alloy-pyroscope-high-frequency.alloy
```

### 4. Set Environment Variables

Ensure your Grafana Cloud API key is set:

```bash
export GCLOUD_RW_API_KEY="your-grafana-cloud-api-key"
```

## Delta vs Snapshot Profiles

### Delta Profiles (`delta = true`)
- **CPU Profile**: Captures CPU usage over scrape duration
- **Wall Profile**: Samples wall clock time over scrape duration
- **Duration**: Automatically set to `scrape_interval - 1`

### Snapshot Profiles (`delta = false`)
- **Heap, Allocs, Goroutine, Block, Mutex**: Instant state snapshots
- **Python Custom Profiles**: Object counts, space usage, exceptions
- **No Duration**: Immediate capture of current state

## Profile.Custom Blocks Explained

The Python-specific endpoints require `profile.custom` blocks because they're not standard Go pprof endpoints:

```hcl
profile.custom "inuse_objects" {
    enabled = true
    path = "/debug/pprof/inuse_objects"
    delta = false
}
```

This tells Alloy:
- Enable scraping this custom endpoint
- Use the specified path
- Treat as snapshot (not duration-based)

## Optimization Recommendations

### For General Monitoring
- Use the standard 30s configuration
- Monitor resource usage on both exporter and Alloy
- Adjust `scrape_interval` based on your specific collection patterns

### For Burst Activity Analysis
- Use the high-frequency configuration
- Focus on CPU and wall profiles during collection windows
- Consider time-based filtering in Grafana for burst analysis

### Resource Considerations

**Exporter Impact**:
- CPU profiling adds minimal overhead when not actively profiling
- Memory profiling (tracemalloc) has constant low overhead
- Duration-based profiles temporarily increase CPU usage during capture

**Network/Storage**:
- High-frequency scraping increases data volume
- Profile size varies: heap/allocs are larger, exceptions are smaller
- Consider retention policies in Grafana Cloud

## Grafana Cloud Configuration

**⚠️ Important**: The URL you provided appears to be for Loki (logs), not Pyroscope (profiles). You'll need to update the endpoint URL.

### Getting Your Pyroscope Endpoint

1. Log in to Grafana Cloud
2. Go to "Connections" → "Add new connection" → "Pyroscope"
3. Your Pyroscope endpoint will look like: `https://profiles-prod-XXX.grafana.net`

### Configuration

```hcl
pyroscope.write "endpoint" {
    endpoint {
        // Update this URL to your actual Pyroscope endpoint
        url = "https://profiles-prod-035.grafana.net" // UPDATE THIS
        basic_auth {
            username = "1175378"
            password = sys.env("GCLOUD_RW_API_KEY")
        }
    }
}
```

### Finding Your Credentials

In Grafana Cloud:
- **URL**: Under "Connections" → "Pyroscope" → "Endpoint URL"
- **Username**: Usually your User ID (found in the connection details)
- **Password**: Generate a new API key with "Metrics:Write" permissions

## Troubleshooting

### Common Issues

1. **"Profiling is disabled" responses**:
   - Ensure `MERAKI_EXPORTER_ENABLE_PROFILING=true`
   - Restart the exporter after setting the variable

2. **Empty CPU profiles**:
   - Normal during idle periods
   - CPU profiles only show data when there's actual CPU activity
   - Use wall profiles to see where time is spent (including waiting)

3. **Connection errors**:
   - Verify exporter is running on localhost:9099
   - Check firewall/network connectivity
   - Ensure `/health` endpoint responds

4. **High resource usage**:
   - Reduce scrape frequency
   - Disable less critical profile types
   - Monitor profile sizes

### Debugging

Enable debug logging in Alloy:

```hcl
logging {
    level = "debug"
    format = "json"
}
```

Check Alloy metrics:
```bash
curl http://localhost:12345/metrics | grep pyroscope
```

## Profile Analysis Tips

### In Grafana Cloud Pyroscope

1. **CPU Analysis**:
   - Focus on function call trees during collection periods
   - Look for unexpected CPU hotspots

2. **Memory Analysis**:
   - Compare heap profiles before/after collections
   - Monitor allocation patterns in allocs profiles

3. **Concurrency Analysis**:
   - Use goroutine profiles to understand thread usage
   - Block/mutex profiles show synchronization issues

4. **Python-Specific**:
   - `inuse_objects` shows object type proliferation
   - `exceptions` helps identify error patterns

### Time Range Selection

- **For burst analysis**: Use 15-minute windows around collection times
- **For trends**: Use hourly/daily views with heap and object profiles
- **For debugging**: Use high-resolution views (1-5 minutes) with CPU profiles

## Advanced Configuration

### Custom Labels

Add environment-specific labels:

```hcl
targets = [
    {
        "__address__" = "localhost:9099",
        "service_name" = "meraki-dashboard-exporter",
        "env" = "staging",           // Change per environment
        "datacenter" = "us-west-2",  // Add datacenter info
        "collector_tier" = "all",    // Indicate which collectors enabled
    },
]
```

### Multiple Exporters

For multiple exporter instances:

```hcl
targets = [
    {"__address__" = "exporter-1:9099", "instance" = "exporter-1"},
    {"__address__" = "exporter-2:9099", "instance" = "exporter-2"},
]
```

This configuration provides comprehensive profiling coverage for your Meraki Dashboard Exporter with the flexibility to optimize for your specific monitoring needs.
