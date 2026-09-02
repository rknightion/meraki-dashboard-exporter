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
_EXEMPTIONS = {
    _SOURCE_ROOT / "collectors" / "devices" / "mr" / "client_logs.py": (
        "api_facade",
        "MRClientLogsCollector creates its facade once in __init__.",
    ),
    _SOURCE_ROOT / "core" / "discovery.py": (
        "api_facade",
        "DiscoveryService creates its facade once in __init__.",
    ),
    _SOURCE_ROOT / "services" / "inventory.py": (
        "_make_api_call",
        "OrganizationInventory delegates through _make_api_call to facade_for(self).call.",
    ),
}


def _sdk_call_violations(source_paths: tuple[Path, ...] | None = None) -> list[str]:
    """Return SDK method references that do not use the approved facade form."""
    violations: list[str] = []
    for root in source_paths or _OWNED_ROOTS:
        candidate_paths = root.rglob("*.py") if root.is_dir() else (root,)
        for path in candidate_paths:
            tree = ast.parse(path.read_text(), filename=str(path))
            parents = _parent_nodes(tree)
            for node in ast.walk(tree):
                if _is_sdk_method(node) and not _is_approved_sdk_argument(node, parents, path):
                    violations.append(f"{_display_path(path)}:{node.lineno}")
    return violations


def _is_sdk_method(node: ast.expr) -> bool:
    """Whether an attribute is a ``self.api.<controller>.<method>`` reference."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Attribute)
        and node.value.value.attr == "api"
        and isinstance(node.value.value.value, ast.Name)
        and node.value.value.value.id == "self"
    )


def _parent_nodes(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Map each parsed node to its immediate parent."""
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _is_approved_sdk_argument(
    node: ast.expr,
    parents: dict[ast.AST, ast.AST],
    path: Path,
) -> bool:
    """Whether a method object is passed through one exact approved facade seam."""
    call = parents.get(node)
    if not isinstance(call, ast.Call) or node not in call.args[1:]:
        return False
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    receiver = func.value
    if (
        func.attr == "call"
        and isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Name)
        and receiver.func.id == "facade_for"
    ):
        return True

    exemption = _EXEMPTIONS.get(path)
    if exemption is None:
        return False
    receiver_name, _reason = exemption
    return (
        isinstance(receiver, ast.Name) and receiver.id == "self" and func.attr == receiver_name
    ) or (
        func.attr == "call"
        and isinstance(receiver, ast.Attribute)
        and isinstance(receiver.value, ast.Name)
        and receiver.value.id == "self"
        and receiver.attr == receiver_name
    )


def _display_path(path: Path) -> str:
    """Render production paths relatively and isolated fixture paths by basename."""
    try:
        return str(path.relative_to(_SOURCE_ROOT))
    except ValueError:
        return path.name


def test_698_no_raw_sdk_thread_calls_outside_facade() -> None:
    """All production SDK endpoints must cross ``MerakiApiFacade.call``."""
    assert _sdk_call_violations() == []


def test_698_rejects_run_in_executor_sdk_bypass(tmp_path: Path) -> None:
    """The gate rejects executor dispatches that skip the facade."""
    source = tmp_path / "executor_bypass.py"
    source.write_text(
        "async def fetch(self, loop):\n"
        "    return await loop.run_in_executor(\n"
        "        None, self.api.organizations.getOrganizationDevices, 'org-id'\n"
        "    )\n"
    )

    assert _sdk_call_violations((source,)) == ["executor_bypass.py:3"]


def test_698_rejects_local_sdk_method_alias_bypass(tmp_path: Path) -> None:
    """The gate rejects aliases that conceal a later raw SDK invocation."""
    source = tmp_path / "alias_bypass.py"
    source.write_text(
        "async def fetch(self):\n"
        "    endpoint = self.api.organizations.getOrganizationDevices\n"
        "    return await asyncio.to_thread(endpoint, 'org-id')\n"
    )

    assert _sdk_call_violations((source,)) == ["alias_bypass.py:2"]
