#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧪 Running unit tests...${NC}"
echo ""

# Change to project root directory
cd "$(dirname "$0")/.."

# Set coverage file for unit tests
export COVERAGE_FILE=.coverage.unit

# Run unit tests with coverage
echo -e "${YELLOW}📊 Running unit tests with coverage...${NC}"
uv run pytest tests/unit/ -v --cov-report=term-missing

echo ""
echo -e "${GREEN}✅ Unit tests completed!${NC}"
