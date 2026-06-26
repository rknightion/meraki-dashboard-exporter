"""AST scan of the codebase for consumed Meraki SDK operations.

Two call forms exist in this codebase and BOTH must be captured:

1. Direct collector calls: ``self.api.<controller>.<method>(...)`` and the
   ``asyncio.to_thread(self.api.<controller>.<method>, ...)`` form.
2. ``AsyncMerakiClient`` wrapper methods in ``api/client.py`` that bind the SDK
   method off a local variable and pass it (plus its operationId as a string
   literal) to ``self._request("opId", api_client.<controller>.<method>, ...)``.

Matching only ``self.api.<ctrl>.<method>`` misses operations consumed solely via
the wrapper, so we union an attribute-chain strategy (keyed on a known Meraki
controller set, which matches any receiver: ``self.api`` *or* ``api_client``)
with extraction of the string-literal first argument to ``_request``.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Top-level Meraki SDK controller sections. A method accessed as
# ``<anything>.<controller>.<method>`` where <controller> is one of these is a
# consumed SDK operation, regardless of whether the receiver is ``self.api`` or
# a local ``api_client`` variable.
MERAKI_CONTROLLERS = frozenset({
    "administered",
    "appliance",
    "batch",
    "camera",
    "campusGateway",
    "cellularGateway",
    "devices",
    "insight",
    "licensing",
    "networks",
    "organizations",
    "secureConnect",
    "sensor",
    "sm",
    "switch",
    "wireless",
})


def _looks_like_operation_id(name: str) -> bool:
    """Meraki operationIds are lowerCamelCase identifiers with no underscores."""
    return bool(name) and name[0].islower() and name.isalnum()


class _OpVisitor(ast.NodeVisitor):
    """Collect consumed operationIds via both call forms."""

    def __init__(self) -> None:
        self.ops: set[str] = set()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Match `<expr>.<controller>.<method>`: node is the `.<method>` access,
        # node.value is `<expr>.<controller>`.
        value = node.value
        if (
            isinstance(value, ast.Attribute)
            and value.attr in MERAKI_CONTROLLERS
            and _looks_like_operation_id(node.attr)
        ):
            self.ops.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Match `self._request("opId", ...)` and capture the string-literal opId.
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "_request"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            self.ops.add(node.args[0].value)
        self.generic_visit(node)


def consumed_operations(src_root: str) -> set[str]:
    """Return the set of consumed Meraki SDK operationIds referenced under src_root."""
    ops: set[str] = set()
    for path in Path(src_root).rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        visitor = _OpVisitor()
        visitor.visit(tree)
        ops |= visitor.ops
    return ops
