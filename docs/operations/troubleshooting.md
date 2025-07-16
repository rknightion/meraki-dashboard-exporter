# Troubleshooting Guide

This guide helps diagnose and resolve common issues with the Meraki Dashboard Exporter.

## Quick Diagnostics

### Health Check

First, verify the exporter is running:

```bash
# Check health endpoint
curl http://localhost:9099/health

# Check if metrics are being exposed
curl -s http://localhost:9099/metrics | grep -c "^meraki_"

# Check specific metric
curl -s http://localhost:9099/metrics | grep "meraki_collector_last_success"
```

### Check Logs

Enable debug logging for detailed information:

```bash
# Set debug logging
export MERAKI_EXPORTER_LOG_LEVEL=DEBUG

# For Docker
docker logs -f meraki-exporter --tail 100

# For Kubernetes
kubectl logs -f deployment/meraki-exporter -n monitoring
```

## Common Issues

### No Metrics Appearing

**Symptoms**: `/metrics` endpoint returns empty or no Meraki metrics

**Possible Causes**:

1. **Invalid API Key**
   ```bash
   # Check for authentication errors in logs
   docker logs meraki-exporter | grep -i "auth\|401"
   ```

   **Solution**: Verify API key is correct and has proper permissions

2. **API Access Not Enabled**
   - Log into Meraki Dashboard
   - Go to Organization > Settings
   - Enable "Dashboard API access"

3. **Network Connectivity**
   ```bash
   # Test API connectivity
   curl -H "X-Cisco-Meraki-API-Key: $MERAKI_API_KEY" \
     https://api.meraki.com/api/v1/organizations
   ```

4. **Wrong API URL**
   - Verify you're using the correct regional endpoint
   - Check `MERAKI_EXPORTER_API_BASE_URL` setting

### API Rate Limiting

**Symptoms**: 429 errors in logs, missing metrics

**Example Log**:
```json
{
  "level": "ERROR",
  "message": "API rate limit exceeded",
  "status_code": 429
}
```

**Solutions**:

1. **Increase Update Intervals**:
   ```yaml
   MERAKI_EXPORTER_FAST_UPDATE_INTERVAL: 120
   MERAKI_EXPORTER_MEDIUM_UPDATE_INTERVAL: 600
   MERAKI_EXPORTER_SLOW_UPDATE_INTERVAL: 1800
   ```

2. **Monitor API Usage**:
   ```promql
   # Check API call rate
   rate(meraki_collector_api_calls_total[5m])
   ```

3. **Reduce Scope**:
   - Monitor specific organization with `MERAKI_EXPORTER_ORG_ID`
   - Disable unnecessary collectors (future feature)

### High Memory Usage

**Symptoms**: Container OOMKilled, high memory consumption

**Diagnosis**:
```bash
# Check memory usage
docker stats meraki-exporter

# For Kubernetes
kubectl top pod -n monitoring | grep meraki
```

**Solutions**:

1. **Increase Memory Limits**:
   ```yaml
   resources:
     limits:
       memory: "1Gi"
     requests:
       memory: "512Mi"
   ```

2. **Reduce Metric Cardinality**:
   - Monitor fewer organizations
   - Use metric relabeling to drop high-cardinality series

3. **Check for Memory Leaks**:
   ```promql
   # Monitor memory growth over time
   container_memory_usage_bytes{pod=~"meraki-exporter.*"}
   ```

### Missing Device Metrics

**Symptoms**: Some devices not appearing in metrics

**Troubleshooting Steps**:

1. **Check Device Status in API**:
   ```bash
   # List all devices
   curl -H "X-Cisco-Meraki-API-Key: $API_KEY" \
     "https://api.meraki.com/api/v1/organizations/$ORG_ID/devices"
   ```

2. **Verify Device is Online**:
   - Check Meraki Dashboard for device status
   - Offline devices may not report all metrics

3. **Check Permissions**:
   - Ensure API key has access to all networks
   - Some device types require specific permissions

### Sensor Metrics Not Updating

**Symptoms**: MT sensor readings are stale or missing

**Common Causes**:

1. **Gateway Offline**: MT sensors require an MR/MX gateway
2. **Fast Tier Disabled**: Check update interval settings
3. **No Sensor Data**: Verify sensors are reporting in Dashboard

**Debug Steps**:
```bash
# Check sensor API directly
curl -H "X-Cisco-Meraki-API-Key: $API_KEY" \
  "https://api.meraki.com/api/v1/organizations/$ORG_ID/sensor/readings/latest"

# Check collector logs
docker logs meraki-exporter | grep -i sensor
```

### Alert Metrics Missing

**Symptoms**: No `meraki_alerts_*` metrics

**Possible Issues**:

1. **Assurance Not Available**: Feature may not be enabled for organization
2. **No Active Alerts**: Metrics only show active (non-dismissed) alerts
3. **API Access**: Check for 404 errors in logs

**Verification**:
```bash
# Check alerts API
curl -H "X-Cisco-Meraki-API-Key: $API_KEY" \
  "https://api.meraki.com/api/v1/organizations/$ORG_ID/assurance/alerts"
```

## Performance Issues

### Slow Metric Collection

**Symptoms**: Prometheus scrape duration warnings, timeouts

**Diagnosis**:
```promql
# Check collection duration
meraki_collector_duration_seconds

# Check scrape duration
prometheus_target_scrape_duration_seconds{job="meraki"}
```

**Solutions**:

1. **Increase Scrape Timeout**:
   ```yaml
   scrape_configs:
     - job_name: 'meraki'
       scrape_interval: 30s
       scrape_timeout: 25s  # Increase timeout
   ```

2. **Optimize Collection**:
   - Reduce number of monitored organizations
   - Increase update intervals
   - Use regional API endpoints

### High CPU Usage

**Symptoms**: Constant high CPU usage

**Common Causes**:
- Large number of devices
- Frequent API calls
- JSON parsing overhead

**Solutions**:
1. Monitor CPU usage patterns
2. Distribute load across multiple instances
3. Increase collection intervals

## Configuration Issues

### Environment Variables Not Working

**Common Mistakes**:

1. **Typos in Variable Names**:
   ```bash
   # Wrong
   MERAKI_API_TOKEN=xxx  # Should be MERAKI_API_KEY

   # Correct
   MERAKI_API_KEY=xxx
   ```

2. **Missing Prefix**:
   ```bash
   # Wrong
   LOG_LEVEL=DEBUG

   # Correct
   MERAKI_EXPORTER_LOG_LEVEL=DEBUG
   ```

3. **Docker Compose Format**:
   ```yaml
   # Wrong
   environment:
     MERAKI_API_KEY=${MERAKI_API_KEY}  # Missing quotes

   # Correct
   environment:
     - MERAKI_API_KEY=${MERAKI_API_KEY}
   ```

### Regional Endpoint Issues

**Symptoms**: API calls failing, unexpected response format

**Solution**: Use correct regional endpoint:
```bash
# Examples
MERAKI_EXPORTER_API_BASE_URL=https://api.meraki.ca/api/v1  # Canada
MERAKI_EXPORTER_API_BASE_URL=https://api.meraki.cn/api/v1  # China
```

## Debugging Techniques

### Enable Verbose Logging

```yaml
environment:
  - MERAKI_EXPORTER_LOG_LEVEL=DEBUG
  - MERAKI_EXPORTER_LOG_FORMAT=console  # Easier to read
```

### API Call Tracing

Monitor specific API calls:
```bash
# Watch for specific API endpoint
docker logs -f meraki-exporter | grep "getOrganizationDevices"

# Count API calls by endpoint
docker logs meraki-exporter | jq -r '.api_method' | sort | uniq -c
```

### Metric Validation

Check if metrics are being set:
```bash
# Check metric values
curl -s http://localhost:9099/metrics | grep "meraki_device_up{" | head -10

# Check metric timestamps
curl -s http://localhost:9099/metrics | grep "meraki_collector_last_success"
```

## Recovery Procedures

### Full Reset

1. **Stop the exporter**:
   ```bash
   docker-compose down
   ```

2. **Clear any persistent data** (if applicable)

3. **Verify configuration**:
   ```bash
   # Test API key
   curl -H "X-Cisco-Meraki-API-Key: $MERAKI_API_KEY" \
     https://api.meraki.com/api/v1/organizations
   ```

4. **Start with minimal config**:
   ```bash
   docker run --rm \
     -e MERAKI_API_KEY="$MERAKI_API_KEY" \
     -e MERAKI_EXPORTER_LOG_LEVEL=DEBUG \
     -p 9099:9099 \
     ghcr.io/rknightion/meraki-dashboard-exporter:latest
   ```

### Incremental Debugging

1. Start with one organization:
   ```bash
   MERAKI_EXPORTER_ORG_ID=123456
   ```

2. Enable one collector at a time (future feature)

3. Gradually increase scope

## Getting Help

### Collect Diagnostic Information

Before reporting issues, collect:

1. **Version information**:
   ```bash
   docker images | grep meraki-dashboard-exporter
   ```

2. **Configuration** (sanitized):
   ```bash
   env | grep MERAKI_EXPORTER | sed 's/API_KEY=.*/API_KEY=REDACTED/'
   ```

3. **Log excerpt**:
   ```bash
   docker logs --tail 1000 meraki-exporter > exporter.log
   ```

4. **Metric samples**:
   ```bash
   curl -s http://localhost:9099/metrics | grep meraki_ > metrics.txt
   ```

### Support Channels

- **GitHub Issues**: [Report bugs](https://github.com/rknightion/meraki-dashboard-exporter/issues)
- **Discussions**: [Ask questions](https://github.com/rknightion/meraki-dashboard-exporter/discussions)
- **Pull Requests**: [Contribute fixes](https://github.com/rknightion/meraki-dashboard-exporter/pulls)

### Debug Checklist

- [ ] API key is valid and has correct permissions
- [ ] API access is enabled in Meraki Dashboard
- [ ] Network connectivity to Meraki API
- [ ] Correct regional endpoint configured
- [ ] No rate limiting issues
- [ ] Sufficient memory allocated
- [ ] Prometheus can reach the exporter
- [ ] Logs show successful collections
