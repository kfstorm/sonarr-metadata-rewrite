#!/usr/bin/env bash

# Coverage combination script
# Combines coverage data from unit and integration tests

set -euo pipefail

echo "📊 Sonarr Metadata Rewrite Coverage Report"
echo "==========================================="

# Check if any coverage files exist
if ! ls .coverage.* 2>/dev/null | grep -q "."; then
    echo "❌ No coverage data files found (.coverage.*)"
    echo "📝 Run tests first with:"
    echo "   ./scripts/run-unit-tests.sh"
    echo "   ./scripts/run-integration-tests.sh"
    exit 1
fi

echo "📁 Found coverage data files:"
ls -la .coverage.* 2>/dev/null | awk '{print "   - " $9 " (" $5 ")"}'

echo ""
echo "🔄 Combining coverage data files..."
uv run coverage combine

if [ ! -f .coverage ]; then
    echo "❌ Failed to combine coverage files"
    exit 1
fi

echo "✅ Coverage data combined successfully"

# Generate terminal report
echo ""
echo "📊 Coverage Report:"
echo "=================="
uv run coverage report

# Generate HTML report
echo ""
echo "📄 Generating HTML report..."
uv run coverage html
echo "✅ HTML report available at htmlcov/index.html"

# Generate XML report for diff-cover
echo ""
echo "📄 Generating XML report for diff-cover..."
uv run coverage xml
echo "✅ XML report available at coverage.xml"

# Show summary statistics
echo ""
echo "📈 Summary:"
TOTAL_COVERAGE=$(uv run coverage report --format=total)
echo "   Total coverage: ${TOTAL_COVERAGE}%"

# Cleanup note
echo ""
echo "💡 To clean coverage data: rm -f .coverage*"
