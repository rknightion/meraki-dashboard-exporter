---
title: Deployment & Operations
description: Production deployment strategies, monitoring best practices, performance optimization, and troubleshooting
tags:
  - deployment
  - operations
  - production
  - docker
  - monitoring
  - troubleshooting
---

# Deployment & Operations

This guide covers deploying the Meraki Dashboard Exporter in production environments using Docker.

## Docker Compose Deployment (Recommended)

The repository includes a production-ready `docker-compose.yml` file for easy deployment.

### Prerequisites

- Docker and Docker Compose installed
- Meraki API key with appropriate permissions

### Quick Start

1. **Clone the repository**:
   ```bash
   git clone https://github.com/rknightion/meraki-dashboard-exporter.git
   cd meraki-dashboard-exporter
   ```

2. **Create environment file**:
   ```bash
   cat > .env << EOF
   MERAKI_API_KEY=your_api_key_here
   MERAKI_EXPORTER_LOG_LEVEL=INFO
   EOF
   ```

3. **Deploy with Docker Compose**:
   ```bash
   docker compose up -d
   ```

4. **Verify deployment**:
   ```bash
   # Check container status
   docker compose ps

   # View logs
   docker compose logs -f meraki_dashboard_exporter

   # Test metrics endpoint
   curl http://localhost:9099/metrics
   ```

### Configuration Options

The `docker-compose.yml` file supports these environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MERAKI_API_KEY` | ✅ | - | Your Meraki Dashboard API key |
| `MERAKI_EXPORTER_ORG_ID` | ❌ | All orgs | Specific organization ID to monitor |
| `MERAKI_EXPORTER_LOG_LEVEL` | ❌ | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `MERAKI_EXPORTER_OTEL_ENABLED` | ❌ | false | Enable OpenTelemetry metrics export |
| `MERAKI_EXPORTER_OTEL_ENDPOINT` | ❌ | - | OpenTelemetry collector endpoint |

Update your `.env` file with the desired configuration and restart:

```bash
docker compose down
docker compose up -d
```

## Docker Run Deployment

For environments where Docker Compose isn't available:

```bash
# Create and run container
docker run -d \
  --name meraki-dashboard-exporter \
  --restart unless-stopped \
  -p 9099:9099 \
  -e MERAKI_API_KEY=your_api_key_here \
  -e MERAKI_EXPORTER_LOG_LEVEL=INFO \
  --security-opt no-new-privileges:true \
  --read-only \
  ghcr.io/rknightion/meraki-dashboard-exporter:latest

# Verify it's running
docker logs meraki-dashboard-exporter
```

## Health Checks

The exporter provides built-in health checking:

```bash
# Health endpoint
curl http://localhost:9099/health

# Metrics availability
curl http://localhost:9099/metrics | head -10

# Ready check (waits for first successful collection)
curl http://localhost:9099/ready
```

Expected responses:
- `/health`: `{"status": "healthy", "timestamp": "..."}`
- `/ready`: `{"status": "ready", "last_collection": "..."}`

## Monitoring the Exporter

### Container Monitoring

Monitor the exporter container itself:

```bash
# Container resource usage
docker stats meraki-dashboard-exporter

# Recent logs
docker logs --tail 50 meraki-dashboard-exporter

# Follow logs in real-time
docker logs -f meraki-dashboard-exporter
```

### Metrics to Monitor

Key metrics for operational monitoring:

```promql
# Exporter uptime
up{job="meraki"}

# Collection success rate
rate(meraki_collector_collections_total{status="success"}[5m])

# API error rate
rate(meraki_collector_errors_total[5m])

# Collection duration
histogram_quantile(0.95, rate(meraki_collector_duration_seconds_bucket[5m]))
```

## Performance Optimization

### Resource Allocation

Recommended resource limits:

```yaml
# In docker-compose.yml (optional)
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '1'
    reservations:
      memory: 256M
      cpus: '0.5'
```

### Large Deployments

For organizations with many devices (>1000):

```bash
# Increase API concurrency
MERAKI_EXPORTER_API_MAX_CONCURRENT_REQUESTS=20

# Adjust batch sizes
MERAKI_EXPORTER_API_BATCH_SIZE=50

# Optional: Monitor specific networks only
MERAKI_EXPORTER_NETWORK_IDS=L_123,L_456,L_789
```

## Troubleshooting

### Common Issues

#### Exporter Won't Start

```bash
# Check logs for startup errors
docker logs meraki-dashboard-exporter

# Common causes:
# - Invalid API key
# - Network connectivity issues
# - Port already in use
```

#### No Metrics Available

```bash
# Verify API connectivity
curl -H "X-Cisco-Meraki-API-Key: YOUR_KEY" \
  https://api.meraki.com/api/v1/organizations

# Check exporter logs for API errors
docker logs meraki-dashboard-exporter | grep -i error
```

#### High Memory Usage

```bash
# Check memory consumption
docker stats meraki-dashboard-exporter --no-stream

# Reduce scope if needed
MERAKI_EXPORTER_ORG_ID=specific_org_id
```

#### API Rate Limiting

```bash
# Check for rate limit errors in logs
docker logs meraki-dashboard-exporter | grep -i "rate limit"

# Monitor API request rate
curl http://localhost:9099/metrics | grep meraki_api_requests_total
```

### Log Analysis

Key log patterns to monitor:

```bash
# Successful collections
docker logs meraki-dashboard-exporter | grep "Collection completed"

# API errors
docker logs meraki-dashboard-exporter | grep "API error"

# Performance warnings
docker logs meraki-dashboard-exporter | grep "slow collection"
```

### Getting Help

If you encounter issues:

1. **Check the logs**: `docker logs meraki-dashboard-exporter`
2. **Verify configuration**: Ensure API key and environment variables are correct
3. **Test connectivity**: Verify network access to `api.meraki.com`
4. **Review metrics**: Check `/metrics` endpoint for error counters
5. **File an issue**: [GitHub Issues](https://github.com/rknightion/meraki-dashboard-exporter/issues) with logs and configuration

## Updating

To update to the latest version:

```bash
# With Docker Compose
docker compose pull
docker compose up -d

# With Docker run
docker pull ghcr.io/rknightion/meraki-dashboard-exporter:latest
docker stop meraki-dashboard-exporter
docker rm meraki-dashboard-exporter
# Then run the docker run command again
```

The exporter supports rolling updates with minimal downtime. Configuration changes require a container restart.
