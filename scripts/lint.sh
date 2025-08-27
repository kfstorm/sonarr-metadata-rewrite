#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default behavior is to fix issues
CHECK_ONLY=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --check)
            CHECK_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--check]"
            echo "  --check    Run checks only (don't fix issues)"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}🔍 Running code quality checks...${NC}"
echo ""

# Function to run a command and capture its exit code
run_check() {
    local name="$1"
    local cmd="$2"
    local emoji="$3"

    echo -e "${YELLOW}${emoji} Running ${name}...${NC}"

    if eval "$cmd"; then
        echo -e "${GREEN}✅ ${name} passed${NC}"
        echo ""
    else
        echo -e "${RED}❌ ${name} failed${NC}"
        echo ""
        overall_success=false
    fi
}

# Track overall success
overall_success=true

# Change to project root directory
cd "$(dirname "$0")/.."

if [ "$CHECK_ONLY" = true ]; then
    echo -e "${BLUE}📋 Running checks only (no fixes will be applied)${NC}"
else
    echo -e "${BLUE}🛠️  Running checks and fixes${NC}"
fi
echo ""

# Set up tool arguments based on CHECK_ONLY flag
if [ "$CHECK_ONLY" = true ]; then
    BLACK_ARGS="--check ."
    BLACK_NAME="Black (code formatting check)"
    BLACK_EMOJI="🎨"
    RUFF_ARGS="check"
    RUFF_NAME="Ruff (linting check)"
    RUFF_EMOJI="🔎"
    MARKDOWN_ARGS="scan *.md"
    MARKDOWN_NAME="PyMarkdownLnt (markdown linting check)"
    MARKDOWN_EMOJI="📝"
else
    BLACK_ARGS="."
    BLACK_NAME="Black (code formatting)"
    BLACK_EMOJI="🎨"
    RUFF_ARGS="check --fix"
    RUFF_NAME="Ruff (linting with auto-fix)"
    RUFF_EMOJI="🔧"
    MARKDOWN_ARGS="fix *.md"
    MARKDOWN_NAME="PyMarkdownLnt (markdown linting with auto-fix)"
    MARKDOWN_EMOJI="📝"
fi

# Black check/format
run_check "$BLACK_NAME" "uv run black $BLACK_ARGS" "$BLACK_EMOJI"

# Ruff check/fix
run_check "$RUFF_NAME" "uv run ruff $RUFF_ARGS" "$RUFF_EMOJI"

# If we applied fixes, run a final Ruff check to ensure everything is clean
if [ "$CHECK_ONLY" = false ]; then
    run_check "Ruff (final linting check)" "uv run ruff check" "🔎"
fi

# MyPy check (no auto-fix available)
run_check "MyPy (type checking)" "uv run mypy" "🔍"

# Vulture check (no auto-fix available) - production code only
run_check "Vulture (dead code detection - production)" "uv run vulture src vulture_whitelist.py" "🦅"

# Vulture check (no auto-fix available) - full scope including tests
run_check "Vulture (dead code detection - full)" "uv run vulture" "🔬"

# Tach dependency validation (no auto-fix available)
run_check "Tach (dependency validation)" "uv run tach check" "📦"

# Tach external dependencies validation (no auto-fix available)
run_check "Tach (external dependencies)" "uv run tach check-external" "🔗"

# Markdown linting/fixing
run_check "$MARKDOWN_NAME" "uv run pymarkdown $MARKDOWN_ARGS" "$MARKDOWN_EMOJI"

echo "=================================="
if [ "$overall_success" = true ]; then
    echo -e "${GREEN}🎉 All checks passed!${NC}"
    exit 0
else
    if [ "$CHECK_ONLY" = true ]; then
        echo -e "${RED}💥 Some checks failed. Run without --check to fix automatically.${NC}"
    else
        echo -e "${RED}💥 Some checks failed. Please fix the remaining issues manually.${NC}"
    fi
    exit 1
fi
