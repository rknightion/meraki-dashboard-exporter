#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v uv >/dev/null 2>&1; then
  RUNNER=(uv run python)
else
  RUNNER=(python3)
fi

"${RUNNER[@]}" "$SCRIPT_DIR/generate_config_docs.py"
"${RUNNER[@]}" "$SCRIPT_DIR/generate_metrics_docs.py"
"${RUNNER[@]}" "$SCRIPT_DIR/generate_collector_docs.py"
"${RUNNER[@]}" "$SCRIPT_DIR/generate_endpoints_docs.py"
