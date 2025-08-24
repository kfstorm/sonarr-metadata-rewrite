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

# Check for TMDB API key
if [ -z "$TMDB_API_KEY" ]; then
    echo -e "${RED}❌ TMDB_API_KEY environment variable is required for integration tests${NC}"
    echo "Please set your TMDB API key:"
    echo "  export TMDB_API_KEY=your_api_key_here"
    exit 1
fi

# Set coverage file for integration tests
export COVERAGE_FILE=.coverage.integration

# Run integration tests
echo -e "${YELLOW}🌐 Running integration tests (requires TMDB API access)...${NC}"
uv run pytest tests/integration/ -v --cov-report=term-missing -m integration

echo ""
echo -e "${GREEN}✅ Integration tests completed!${NC}"
