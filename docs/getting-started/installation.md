# Installation

This guide covers the different ways to install and run the Meraki Dashboard Exporter.

## Prerequisites

Before installing, ensure you have:

- A Meraki Dashboard account with API access enabled
- A valid API key (see [Meraki documentation](https://documentation.meraki.com/General_Administration/Other_Topics/Cisco_Meraki_Dashboard_API))
- Network connectivity to the Meraki API endpoints

## Installation Methods

### Docker (Recommended)

The easiest way to run the exporter is using the pre-built Docker image:

```bash
docker pull ghcr.io/rknightion/meraki-dashboard-exporter:latest
```

#### Running with Docker

```bash
docker run -d \
  --name meraki-exporter \
  -e MERAKI_API_KEY="your_api_key_here" \
  -p 9099:9099 \
  ghcr.io/rknightion/meraki-dashboard-exporter:latest
```

#### Docker Compose

Create a `docker-compose.yml` file:

```yaml
services:
  meraki-exporter:
    image: ghcr.io/rknightion/meraki-dashboard-exporter:latest
    container_name: meraki-exporter
    restart: unless-stopped
    ports:
      - "9099:9099"
    environment:
      - MERAKI_API_KEY=${MERAKI_API_KEY}
      - MERAKI_EXPORTER_LOG_LEVEL=${LOG_LEVEL:-INFO}
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:9099/health').raise_for_status()"]
      interval: 30s
      timeout: 10s
      retries: 3
```

Then run:

```bash
docker-compose up -d
```

### Python Installation

For development or custom deployments, you can install directly with Python:

#### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/rknightion/meraki-dashboard-exporter.git
cd meraki-dashboard-exporter

# Install with uv
uv pip install -e .
```

#### Using pip

```bash
# Clone the repository
git clone https://github.com/rknightion/meraki-dashboard-exporter.git
cd meraki-dashboard-exporter

# Install with pip
pip install -e .
```

### Kubernetes

For Kubernetes deployments, use the following manifest:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: meraki-exporter
  labels:
    app: meraki-exporter
spec:
  replicas: 1
  selector:
    matchLabels:
      app: meraki-exporter
  template:
    metadata:
      labels:
        app: meraki-exporter
    spec:
      containers:
      - name: meraki-exporter
        image: ghcr.io/rknightion/meraki-dashboard-exporter:latest
        ports:
        - containerPort: 9099
          name: metrics
        env:
        - name: MERAKI_API_KEY
          valueFrom:
            secretKeyRef:
              name: meraki-api-key
              key: api-key
        livenessProbe:
          httpGet:
            path: /health
            port: 9099
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 9099
          initialDelaySeconds: 10
          periodSeconds: 10
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: meraki-exporter
  labels:
    app: meraki-exporter
spec:
  ports:
  - port: 9099
    targetPort: 9099
    name: metrics
  selector:
    app: meraki-exporter
```

## Verifying Installation

After installation, verify the exporter is running:

### Check Health Endpoint

```bash
curl http://localhost:9099/health
```

Expected response:
```json
{"status": "healthy"}
```

### Check Metrics Endpoint

```bash
curl http://localhost:9099/metrics | grep meraki
```

You should see Meraki metrics being exposed.

### Check Logs

=== "Docker"

    ```bash
    docker logs meraki-exporter
    ```

=== "Docker Compose"

    ```bash
    docker-compose logs meraki-exporter
    ```

=== "Python"

    Check the console output where you ran the exporter.

## Container Security

The Docker image includes several security features:

- Runs as non-root user (UID 1000)
- Read-only filesystem
- No new privileges flag
- Minimal base image (Python slim)
- Health checks included

## Next Steps

- [Configure the exporter](configuration.md) for your environment
- Follow the [Quick Start guide](quickstart.md) to begin collecting metrics
- Set up [Prometheus integration](../integration/prometheus.md)
