#!/bin/bash
# Test script for Docker builds with detailed output

set -euo pipefail

echo "🔍 Testing Docker build for meraki-dashboard-exporter"
echo "=================================================="

# Enable BuildKit
export DOCKER_BUILDKIT=1

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Test basic build
echo -e "\n${YELLOW}1. Building Docker image...${NC}"
if docker build --progress=plain -t meraki-dashboard-exporter:test .; then
    echo -e "${GREEN}✅ Build successful${NC}"
else
    echo -e "${RED}❌ Build failed${NC}"
    exit 1
fi

# Test image metadata
echo -e "\n${YELLOW}2. Checking image metadata...${NC}"
docker inspect meraki-dashboard-exporter:test | jq -r '.[0].Config.Labels'

# Test running as non-root
echo -e "\n${YELLOW}3. Verifying non-root user...${NC}"
USER=$(docker run --rm meraki-dashboard-exporter:test whoami)
if [ "$USER" = "exporter" ]; then
    echo -e "${GREEN}✅ Running as non-root user: $USER${NC}"
else
    echo -e "${RED}❌ Not running as expected user. Got: $USER${NC}"
    exit 1
fi

# Test Python environment
echo -e "\n${YELLOW}4. Checking Python environment...${NC}"
docker run --rm meraki-dashboard-exporter:test python -c "import sys; print(f'Python {sys.version}')"
docker run --rm meraki-dashboard-exporter:test python -c "import meraki_dashboard_exporter; print('✅ Package imported successfully')"

# Test entrypoint
echo -e "\n${YELLOW}5. Testing entrypoint...${NC}"
if docker run --rm meraki-dashboard-exporter:test --help > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Entrypoint works${NC}"
else
    echo -e "${RED}❌ Entrypoint failed${NC}"
    exit 1
fi

# Check installed packages
echo -e "\n${YELLOW}6. Listing installed packages...${NC}"
docker run --rm meraki-dashboard-exporter:test pip list | grep -E "(meraki|prometheus|fastapi|uvicorn)" || true

echo -e "\n${GREEN}✅ All tests passed!${NC}"
