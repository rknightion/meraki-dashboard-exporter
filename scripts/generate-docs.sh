#!/bin/bash
# Documentation generation script
# Generates both metrics and configuration documentation

set -e

echo "🔄 Generating documentation..."
echo ""

# Generate metrics documentation
echo "📊 Generating metrics documentation..."
if uv run python src/meraki_dashboard_exporter/tools/generate_metrics_docs.py; then
    echo "   ✅ Metrics documentation generated: docs/metrics/metrics.md"
else
    echo "   ❌ Failed to generate metrics documentation"
    exit 1
fi

echo ""

# Generate configuration documentation
echo "⚙️  Generating configuration documentation..."
if uv run python -m meraki_dashboard_exporter.tools.generate_config_docs; then
    echo "   ✅ Configuration documentation generated: docs/config.md"
else
    echo "   ❌ Failed to generate configuration documentation"
    exit 1
fi

echo ""

# Generate collector documentation
echo "🏗️  Generating collector documentation..."
if uv run python src/meraki_dashboard_exporter/tools/generate_collector_docs.py; then
    echo "   ✅ Collector documentation generated: docs/collectors.md"
else
    echo "   ❌ Failed to generate collector documentation"
    exit 1
fi

echo ""
echo "✅ Documentation generation completed successfully!"

# Check if there are any git changes
if git diff --quiet docs/; then
    echo "   📄 No documentation changes detected"
else
    echo "   📝 Documentation files have been updated:"
    git diff --name-only docs/ | sed 's/^/     - /'
    echo ""
    echo "   💡 Don't forget to commit these changes:"
    echo "      git add docs/"
    echo "      git commit -m 'docs: update generated documentation'"
fi
