"""Regression gate for the one-way Meraki SDK facade boundary (#698)."""

from __future__ import annotations

import ast
from pathlib import Path

_SOURCE_ROOT = Path(__file__).parents[2] / "src" / "meraki_dashboard_exporter"
_OWNED_ROOTS = (
    _SOURCE_ROOT / "api",
    _SOURCE_ROOT / "services",
    _SOURCE_ROOT / "collectors",
    _SOURCE_ROOT / "core" / "api_helpers.py",
    _SOURCE_ROOT / "core" / "discovery.py",
)
_EXCEPTIONS = {
    _SOURCE_ROOT / "collectors" / "devices" / "mr" / "client_logs.py",
}


def _bare_sdk_thread_calls() -> list[str]:
    """Return raw ``asyncio.to_thread`` uses outside the facade boundary."""
    violations: list[str] = []
    for root in _OWNED_ROOTS:
        paths = root.rglob("*.py") if root.is_dir() else (root,)
        for path in paths:
            if path in _EXCEPTIONS:
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or len(node.args) < 1:
                    continue
                func = node.func
                if not (
                    isinstance(func, ast.Attribute)
                    and func.attr == "to_thread"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "asyncio"
                ):
                    continue
                target = node.args[0]
                if _is_sdk_method(target):
                    violations.append(f"{path.relative_to(_SOURCE_ROOT)}:{node.lineno}")
    return violations


def _is_sdk_method(node: ast.expr) -> bool:
    """Whether an attribute access is rooted at ``self.api`` or an API parameter."""
    while isinstance(node, ast.Attribute):
        if node.attr == "api" and isinstance(node.value, ast.Name) and node.value.id == "self":
            return True
        node = node.value
    return isinstance(node, ast.Name) and node.id == "api"


def test_698_no_raw_sdk_thread_calls_outside_facade() -> None:
    """All production SDK endpoints must cross ``MerakiApiFacade.call``."""
    assert _bare_sdk_thread_calls() == []
