"""Regression coverage for SDK exhausted-retry response normalization (#706)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    ("source_file", "function_name"),
    [
        (
            "src/meraki_dashboard_exporter/collectors/devices/ms_stack.py",
            "collect_for_network",
        ),
        (
            "src/meraki_dashboard_exporter/collectors/devices/mt.py",
            "_fetch_sensor_devices",
        ),
        (
            "src/meraki_dashboard_exporter/collectors/devices/ms.py",
            "collect_stp_priorities",
        ),
        (
            "src/meraki_dashboard_exporter/collectors/devices/mv.py",
            "_collect_analytics_zones",
        ),
    ],
)
def test_exhausted_retry_fetches_use_response_normalizer(
    source_file: str, function_name: str
) -> None:
    """Every audited response fetch delegates error shapes to the shared normalizer."""
    tree = ast.parse((_ROOT / source_file).read_text())
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )

    normalizers = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_response_format"
    ]

    assert normalizers, f"{source_file}:{function_name} bypasses validate_response_format"
