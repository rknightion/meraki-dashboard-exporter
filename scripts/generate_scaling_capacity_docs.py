#!/usr/bin/env python3
"""Generate the source-derived network-health capacity region in the scaling guide."""

from __future__ import annotations

import ast
import math
from pathlib import Path

BEGIN = "<!-- BEGIN GENERATED NETWORK HEALTH CAPACITY -->"
END = "<!-- END GENERATED NETWORK HEALTH CAPACITY -->"


def find_repo_root(start_path: Path) -> Path:
    """Find the repository root by walking upwards."""
    for candidate in [start_path, *start_path.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    raise FileNotFoundError("Could not locate repository root (pyproject.toml + src)")


def _endpoint_group_calls(src_path: Path) -> list[ast.Call]:
    source = src_path / "meraki_dashboard_exporter" / "collectors" / "device.py"
    if not source.exists():
        return []
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "DeviceCollector":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign) or not isinstance(
                statement.value, ast.Tuple
            ):
                continue
            if (
                not isinstance(statement.target, ast.Name)
                or statement.target.id != "endpoint_groups"
            ):
                continue
            calls = [item for item in statement.value.elts if isinstance(item, ast.Call)]
            if len(calls) != len(statement.value.elts) or not calls:
                raise RuntimeError(
                    "DeviceCollector.endpoint_groups has an unsupported shape"
                )
            return calls
    return []


def _evaluate_cost(node: ast.AST, shape: dict[str, int]) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in ("shape", "s")
    ):
        attr = node.attr
        if attr in shape:
            return float(shape[attr])
        defaults = {
            "device_count": float(shape.get("ap_count", 1000)),
            "ap_count": float(shape.get("ap_count", 1000)),
            "switch_count": 10.0,
            "mx_count": 5.0,
            "appliance_count": 5.0,
            "camera_count": 10.0,
            "sensor_count": 10.0,
            "network_count": float(shape.get("wireless_network_count", 1)),
            "wireless_network_count": float(shape.get("wireless_network_count", 1)),
            "switch_network_count": float(shape.get("wireless_network_count", 1)),
            "sensor_network_count": float(shape.get("wireless_network_count", 1)),
            "appliance_network_count": float(shape.get("wireless_network_count", 1)),
            "camera_network_count": float(shape.get("wireless_network_count", 1)),
            "org_count": 1.0,
        }
        if attr in defaults:
            return defaults[attr]
        return float(shape.get(attr, 1.0))
    if isinstance(node, ast.BinOp):
        left = _evaluate_cost(node.left, shape)
        right = _evaluate_cost(node.right, shape)
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Add):
            return left + right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "pages":
        if len(node.args) != 2:
            raise RuntimeError("pages() cost function must have exactly two arguments")
        return float(
            math.ceil(_evaluate_cost(node.args[0], shape) / _evaluate_cost(node.args[1], shape))
        )
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "float"
        and len(node.args) == 1
    ):
        return _evaluate_cost(node.args[0], shape)
    raise RuntimeError("Unsupported network-health endpoint-group cost function")


def capacity_costs(src_path: Path, shape: dict[str, int]) -> tuple[float, float]:
    """Return 300-second steady-state equivalent and one all-groups due sweep cost."""
    steady = 0.0
    due_sweep = 0.0
    for call in _endpoint_group_calls(src_path):
        keywords = {
            keyword.arg: keyword.value for keyword in call.keywords if keyword.arg is not None
        }
        floor = keywords.get("floor_seconds")
        cost_fn = keywords.get("cost_fn")
        if not isinstance(floor, ast.Constant) or not isinstance(floor.value, int):
            raise RuntimeError("Endpoint group floor_seconds must be an integer literal")
        if not isinstance(cost_fn, ast.Lambda):
            raise RuntimeError("Endpoint group cost_fn must be a lambda")
        cost = _evaluate_cost(cost_fn.body, shape)
        due_sweep += cost
        steady += cost * 300 / floor.value
    return steady, due_sweep


def _format(value: float, precision: int = 1) -> str:
    return f"{value:,.{precision}f}" if value % 1 else f"{value:,.0f}"


def render_network_health_capacity(src_path: Path) -> str:
    """Render capacity examples from the current endpoint-group AST declarations."""
    homelab, homelab_sweep = capacity_costs(
        src_path, {"wireless_network_count": 1, "ap_count": 1000}
    )
    large, large_sweep = capacity_costs(src_path, {"wireless_network_count": 400, "ap_count": 4000})
    return "\n".join([
        "### Network-health capacity (generated from endpoint groups)",
        "",
        "These figures are derived from `NetworkHealthCollector.endpoint_groups`. "
        "The steady-state number weights each group by `300 / floor_seconds`; "
        "it is not the cost of one simultaneous due sweep.",
        "",
        "| Shape | Steady-state equivalent (calls/300 s) | One all-groups due sweep |",
        "|---|---:|---:|",
        f"| HOMELAB (`W=1`, `AP=1,000`) | **{_format(homelab, 2)}** | {_format(homelab_sweep)} |",
        f"| `W=400`, `AP=4,000` | **{_format(large)}** | {_format(large_sweep)} |",
        "",
        "A due sweep is larger because it includes every windowed group at once; "
        "use the steady-state equivalent for API-budget planning and the due-sweep "
        "column when judging a single collection run against its timeout.",
    ])


def replace_generated_region(guide: Path, rendered: str) -> None:
    """Replace the owned marker-delimited guide region or fail loudly if it is absent."""
    text = guide.read_text(encoding="utf-8")
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) > text.index(END):
        raise RuntimeError(
            f"Scaling-guide generated-region markers are missing or malformed in {guide}"
        )
    before, _, rest = text.partition(BEGIN)
    _, _, after = rest.partition(END)
    guide.write_text(f"{before}{BEGIN}\n{rendered}\n{END}{after}", encoding="utf-8")


def main() -> None:
    """Generate the network-health capacity region."""
    repo_root = find_repo_root(Path(__file__).resolve())
    replace_generated_region(
        repo_root / "docs" / "scaling-guide.md", render_network_health_capacity(repo_root / "src")
    )


if __name__ == "__main__":
    main()
