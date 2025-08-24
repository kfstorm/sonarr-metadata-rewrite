#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Setting up development environment...${NC}"
echo ""

# Change to project root directory
cd "$(dirname "$0")/.."

# Install development dependencies
echo -e "${YELLOW}📦 Installing development dependencies...${NC}"
uv sync --group dev

# Install pre-commit hooks
echo -e "${YELLOW}🔗 Installing pre-commit hooks...${NC}"
uv run pre-commit install

echo ""
echo -e "${GREEN}✅ Development environment setup complete!${NC}"
echo ""
echo "Available commands:"
echo "  ./scripts/lint.sh         - Run all checks and fixes"
echo "  ./scripts/lint.sh --check - Run checks only (no fixes)"
echo "  uv run pre-commit run --all-files - Run pre-commit on all files"
echo ""
echo "Pre-commit hooks are now installed and will run automatically on commit."
