"""Page-aware bulk request construction stays bounded (#699)."""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).parents[2]


def test_org_wide_switch_fetches_do_not_expand_every_serial_into_the_url() -> None:
    """Org-wide endpoints rely on org scope and pagination rather than serial filters."""
    for function_name in ("collect_port_statuses_by_switch", "collect_port_usage_by_switch"):
        tree = ast.parse(
            (_ROOT / "src/meraki_dashboard_exporter/collectors/devices/ms.py").read_text()
        )
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        )
        facade_calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "call"
        ]
        assert facade_calls
        assert all(
            "serials" not in {keyword.arg for keyword in call.keywords} for call in facade_calls
        )
