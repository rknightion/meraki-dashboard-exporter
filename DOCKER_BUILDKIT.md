# Docker BuildKit Guide

This guide explains how to use Docker BuildKit for building multi-architecture images locally.

## Quick Start

We've included a Makefile that automatically enables BuildKit:

```bash
# Build for your current architecture
make docker-build

# Build for all supported architectures
make docker-build-all

# Setup BuildKit builder for advanced features
make buildkit-setup
```

## Manual BuildKit Usage

### Enable BuildKit

BuildKit can be enabled in several ways:

```bash
# Method 1: Environment variable (temporary)
export DOCKER_BUILDKIT=1

# Method 2: Docker configuration (permanent)
echo '{"features":{"buildkit":true}}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker

# Method 3: Docker Compose
export COMPOSE_DOCKER_CLI_BUILD=1
```

### Create a Multi-Architecture Builder

```bash
# Create a new builder instance
docker buildx create --name multiarch --driver docker-container --use

# Bootstrap the builder
docker buildx inspect --bootstrap

# List available builders
docker buildx ls
```

### Build Multi-Architecture Images

```bash
# Build for multiple platforms (without pushing)
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  --tag meraki-dashboard-exporter:latest \
  .

# Build and load for current architecture only
docker buildx build \
  --load \
  --tag meraki-dashboard-exporter:latest \
  .

# Build for all our supported platforms
docker buildx build \
  --platform linux/386,linux/amd64,linux/arm/v5,linux/arm/v7,linux/arm64/v8,linux/ppc64le,linux/s390x \
  --tag meraki-dashboard-exporter:latest \
  .
```

### Advanced BuildKit Features

#### 1. Cache Management

```bash
# Use local cache
docker buildx build \
  --cache-from type=local,src=/tmp/.buildx-cache \
  --cache-to type=local,dest=/tmp/.buildx-cache,mode=max \
  .

# Use registry cache
docker buildx build \
  --cache-from type=registry,ref=ghcr.io/rknightion/meraki-dashboard-exporter:buildcache \
  --cache-to type=registry,ref=ghcr.io/rknightion/meraki-dashboard-exporter:buildcache,mode=max \
  .
```

#### 2. Build Progress Output

```bash
# Plain output (good for CI)
docker buildx build --progress=plain .

# Fancy terminal output (default)
docker buildx build --progress=auto .

# Raw output
docker buildx build --progress=rawjson .
```

#### 3. Inspect Multi-Arch Images

```bash
# View manifest for multi-arch image
docker buildx imagetools inspect meraki-dashboard-exporter:latest

# Create manifest from platform-specific images
docker buildx imagetools create \
  --tag meraki-dashboard-exporter:latest \
  meraki-dashboard-exporter:latest-amd64 \
  meraki-dashboard-exporter:latest-arm64
```

## Platform Notes

### Supported Platforms

Our Python base image (`python:3.13-slim-bookworm`) supports:
- `linux/386` - 32-bit x86
- `linux/amd64` - 64-bit x86 (Intel/AMD)
- `linux/arm/v5` - ARMv5 (very old ARM)
- `linux/arm/v7` - ARMv7 (32-bit ARM, Raspberry Pi 2/3)
- `linux/arm64/v8` - ARMv8 (64-bit ARM, Raspberry Pi 4/5, Apple Silicon, AWS Graviton)
- `linux/ppc64le` - PowerPC 64-bit Little Endian
- `linux/s390x` - IBM Z mainframes

### Local Development Tips

1. **Apple Silicon Macs**: Use `--platform linux/arm64` for native speed
2. **Testing ARM on x86**: BuildKit uses QEMU emulation (slower but works)
3. **CI/CD**: Use `--push` directly instead of `--load` for multi-arch

### Troubleshooting

#### "Multiple platforms feature is currently not supported for docker driver"

```bash
# Switch to docker-container driver
docker buildx create --use --driver docker-container
```

#### "Cannot load multi-platform images"

Multi-platform images can't be loaded into local Docker. Either:
- Build for current platform only: `--platform linux/amd64`
- Push to registry: add `--push`
- Save to file: `--output type=oci,dest=image.tar`

#### Slow ARM builds on x86

This is normal - QEMU emulation is used. Consider:
- Using native ARM runners in CI
- Cross-compilation where possible
- Caching aggressively

## Testing Your Build

We include a test script to verify Docker builds:

```bash
# Run comprehensive Docker build tests
./scripts/test-docker-build.sh

# Or use the Makefile
make docker-test
```

## Performance Tips

1. **Layer Caching**: Order Dockerfile commands from least to most frequently changing
2. **Multi-Stage Builds**: Our Dockerfile uses this - dependencies built once, shared across platforms
3. **uv for Fast Installs**: We use uv which is significantly faster than pip
4. **.dockerignore**: Exclude unnecessary files from build context
5. **Frozen Lockfile**: `uv sync --frozen` ensures reproducible builds

## Security Considerations

1. **Base Image**: Using official Python images ensures security updates
2. **Non-Root User**: Container runs as UID 1000 by default
3. **Minimal Dependencies**: Only required runtime packages installed
4. **SBOM Generation**: BuildKit can generate Software Bill of Materials

```bash
# Generate SBOM during build
docker buildx build \
  --sbom=true \
  --tag meraki-dashboard-exporter:latest \
  .
```
