#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔄 Running integration tests...${NC}"
echo ""

# Change to project root directory
cd "$(dirname "$0")/.."

# Set coverage file for integration tests
export COVERAGE_FILE=.coverage.integration

# Install dependencies if needed (including testcontainers)
echo -e "${YELLOW}📦 Ensuring test dependencies are installed...${NC}"
uv sync --group dev

# Run integration tests
echo -e "${YELLOW}🌐 Running integration tests...${NC}"
echo ""

# Run with increased verbosity and timeout for container operations
uv run pytest tests/integration/ -v --cov-report=term-missing -m integration --tb=short

echo ""
echo -e "${GREEN}✅ Integration tests completed!${NC}"
