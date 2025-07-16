# Quick Start Guide

Get the Meraki Dashboard Exporter up and running in minutes with this step-by-step guide.

## Prerequisites

Before starting, ensure you have:

- [ ] Docker installed (or Python 3.11+)
- [ ] A Meraki Dashboard account
- [ ] API access enabled in your Meraki Dashboard
- [ ] Your Meraki API key

!!! tip "Getting your API Key"
    1. Log in to the [Meraki Dashboard](https://dashboard.meraki.com)
    2. Navigate to **Organization > Settings**
    3. Check **Enable access to the Cisco Meraki Dashboard API**
    4. Go to **My Profile** (top right)
    5. Under **API access**, click **Generate new API key**

## Step 1: Create Configuration

Create a `.env` file with your API key:

```bash
cat > .env << EOF
MERAKI_API_KEY=your_actual_api_key_here
MERAKI_EXPORTER_LOG_LEVEL=INFO
EOF
```

!!! warning "Security Note"
    Never commit your `.env` file to version control. Add it to `.gitignore`.

## Step 2: Run the Exporter

=== "Docker Compose (Recommended)"

    Create a `docker-compose.yml` file:

    ```yaml
    services:
      meraki-exporter:
        image: ghcr.io/rknightion/meraki-dashboard-exporter:latest
        container_name: meraki-exporter
        restart: unless-stopped
        ports:
          - "9099:9099"
        env_file:
          - .env
        healthcheck:
          test: ["CMD", "curl", "-f", "http://localhost:9099/health"]
          interval: 30s
          timeout: 10s
          retries: 3
    ```

    Then run:
    ```bash
    docker-compose up -d
    ```

=== "Docker CLI"

    ```bash
    docker run -d \
      --name meraki-exporter \
      --env-file .env \
      -p 9099:9099 \
      --restart unless-stopped \
      ghcr.io/rknightion/meraki-dashboard-exporter:latest
    ```

=== "Python"

    ```bash
    # Clone the repository
    git clone https://github.com/rknightion/meraki-dashboard-exporter.git
    cd meraki-dashboard-exporter

    # Install dependencies
    uv pip install -e .

    # Run the exporter
    source .env && python -m meraki_dashboard_exporter
    ```

## Step 3: Verify It's Working

### Check the Health Endpoint

```bash
curl http://localhost:9099/health
```

Expected response:
```json
{"status": "healthy"}
```

### Check Metrics Are Being Exposed

```bash
# Count the number of metrics
curl -s http://localhost:9099/metrics | grep -c "^meraki_"

# View some metrics
curl -s http://localhost:9099/metrics | grep "meraki_org_" | head -10
```

### Check the Logs

```bash
# Docker Compose
docker-compose logs -f meraki-exporter

# Docker CLI
docker logs -f meraki-exporter
```

You should see logs like:
```json
{"timestamp": "2024-01-15T10:00:00Z", "level": "INFO", "message": "Starting Meraki Dashboard Exporter"}
{"timestamp": "2024-01-15T10:00:01Z", "level": "INFO", "message": "Discovered 1 organization(s)"}
{"timestamp": "2024-01-15T10:00:02Z", "level": "INFO", "message": "Metrics server started on 0.0.0.0:9099"}
```

## Step 4: Connect Prometheus

Add the exporter to your Prometheus configuration:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'meraki'
    static_configs:
      - targets: ['meraki-exporter:9099']
    scrape_interval: 30s
    scrape_timeout: 25s
```

## Step 5: Import Grafana Dashboard

1. Open Grafana
2. Go to **Dashboards** → **Import**
3. Import our pre-built dashboards:
   - Organization Overview
   - Device Status
   - Sensor Monitoring
   - Alert Dashboard

!!! info "Dashboard JSON files"
    Dashboard JSON files are available in the [GitHub repository](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/dashboards).

## Common First Steps

### Monitor a Specific Organization

If you have access to multiple organizations, you can monitor just one:

```bash
# Add to your .env file
MERAKI_EXPORTER_ORG_ID=123456
```

### Adjust Collection Intervals

For testing, you might want faster updates:

```bash
# Add to your .env file
MERAKI_EXPORTER_FAST_UPDATE_INTERVAL=30
MERAKI_EXPORTER_MEDIUM_UPDATE_INTERVAL=120
```

### Enable Debug Logging

To see detailed API calls and metric updates:

```bash
# Add to your .env file
MERAKI_EXPORTER_LOG_LEVEL=DEBUG
```

## Troubleshooting Quick Fixes

### No Metrics Appearing

1. Check your API key is correct
2. Verify API access is enabled in Meraki Dashboard
3. Check the logs for error messages

### API Rate Limiting

If you see 429 errors:
1. Increase update intervals
2. Monitor fewer organizations
3. Check your API rate limit in Meraki Dashboard

### Connection Errors

1. Verify network connectivity to api.meraki.com
2. Check if you need to use a regional endpoint
3. Verify any proxy settings

## What's Next?

Now that you have the exporter running:

1. **Explore Metrics**: See the [Metrics Reference](../metrics/overview.md) for all available metrics
2. **Set Up Monitoring**: Configure [Prometheus alerts](../integration/prometheus.md#alerting-rules)
3. **Create Dashboards**: Build custom [Grafana dashboards](../integration/grafana.md)
4. **Production Deployment**: Follow our [deployment guide](../operations/deployment.md)

## Getting Help

- Check the [Troubleshooting Guide](../operations/troubleshooting.md)
- Search [GitHub Issues](https://github.com/rknightion/meraki-dashboard-exporter/issues)
- Join the [Discussions](https://github.com/rknightion/meraki-dashboard-exporter/discussions)
