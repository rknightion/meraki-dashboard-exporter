#!/usr/bin/env python3
"""Generate documentation for all collectors in the exporter.

This script scans the codebase to find all collector definitions and generates
a markdown document describing their purpose, metrics, API endpoints used,
update tiers, and relationships.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

TIER_MAP = {
    "UpdateTier.FAST": "FAST",
    "UpdateTier.MEDIUM": "MEDIUM",
    "UpdateTier.SLOW": "SLOW",
}

COLLECTOR_NOTES = {
    "ClientsCollector": "Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true",
}


class CollectorVisitor(ast.NodeVisitor):
    """AST visitor to find collector definitions and their properties."""

    def __init__(self, filepath: Path, repo_root: Path) -> None:
        """Initialize visitor."""
        self.filepath = filepath
        self.repo_root = repo_root
        self.collectors: list[dict[str, Any]] = []
        self.current_class: str | None = None
        self.current_class_info: dict[str, Any] = {}
        self.imports: dict[str, str] = {}  # Maps imported names to their modules

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Track imports for resolving decorator references."""
        if node.module:
            for alias in node.names:
                imported_name = alias.asname if alias.asname else alias.name
                self.imports[imported_name] = f"{node.module}.{alias.name}"
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition to find collectors."""
        old_class = self.current_class
        old_info = self.current_class_info

        self.current_class = node.name
        self.current_class_info = {
            "name": node.name,
            "file": str(self.filepath.relative_to(self.repo_root)),
            "line": node.lineno,
            "docstring": ast.get_docstring(node),
            "base_classes": [],
            "decorators": [],
            "update_tier": None,
            "metrics": [],
            "api_calls": [],
            "sub_collectors": [],
            "registered": False,
        }

        # Extract base classes
        for base in node.bases:
            if isinstance(base, ast.Name):
                self.current_class_info["base_classes"].append(base.id)
            elif isinstance(base, ast.Attribute):
                # Handle qualified names like module.ClassName
                parts = []
                current = base
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                    self.current_class_info["base_classes"].append(".".join(reversed(parts)))

        # Extract decorators
        for decorator in node.decorator_list:
            decorator_info = self._extract_decorator_info(decorator)
            if decorator_info:
                self.current_class_info["decorators"].append(decorator_info)
                # Check for register_collector decorator
                if decorator_info["name"] == "register_collector":
                    if decorator_info.get("args"):
                        self.current_class_info["update_tier"] = decorator_info["args"][0]
                    self.current_class_info["registered"] = True

        # Only process classes that look like collectors
        if self._is_collector_class():
            self.generic_visit(node)
            self.collectors.append(self.current_class_info)
        else:
            self.generic_visit(node)

        self.current_class = old_class
        self.current_class_info = old_info

    def _extract_decorator_info(self, decorator: ast.expr) -> dict[str, Any] | None:
        """Extract information from a decorator."""
        if isinstance(decorator, ast.Name):
            return {"name": decorator.id, "args": []}
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                name = decorator.func.id
                args = []
                for arg in decorator.args:
                    if isinstance(arg, ast.Name):
                        args.append(arg.id)
                    elif isinstance(arg, ast.Attribute):
                        # Handle UpdateTier.MEDIUM etc.
                        if isinstance(arg.value, ast.Name):
                            args.append(f"{arg.value.id}.{arg.attr}")
                    elif isinstance(arg, ast.Constant):
                        args.append(arg.value)
                return {"name": name, "args": args}
        return None

    def _is_collector_class(self) -> bool:
        """Check if the current class is a collector."""
        if not self.current_class:
            return False

        # Check base classes
        for base in self.current_class_info["base_classes"]:
            if "Collector" in base:
                return True

        # Check for register_collector decorator
        for decorator in self.current_class_info["decorators"]:
            if decorator["name"] == "register_collector":
                return True

        # Check class name
        if self.current_class.endswith("Collector"):
            return True

        return False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions to find metrics and API calls."""
        if not self.current_class or not self._is_collector_class():
            self.generic_visit(node)
            return

        # Look for _initialize_metrics method
        if node.name == "_initialize_metrics":
            self._extract_metrics_from_method(node)

        # Look for API calls in any method
        self._extract_api_calls_from_method(node)

        # Look for sub-collector initialization
        if node.name == "__init__":
            self._extract_sub_collectors_from_init(node)

        self.generic_visit(node)

    def _extract_metrics_from_method(self, node: ast.FunctionDef) -> None:
        """Extract metric definitions from _initialize_metrics method."""
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign):
                # Look for self._metric_name = self._create_...
                if (
                    len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Attribute)
                    and isinstance(stmt.targets[0].value, ast.Name)
                    and stmt.targets[0].value.id == "self"
                    and isinstance(stmt.value, ast.Call)
                    and isinstance(stmt.value.func, ast.Attribute)
                ):
                    func_name = stmt.value.func.attr
                    if func_name.startswith("_create_"):
                        metric_type = func_name.replace("_create_", "")
                        metric_var = stmt.targets[0].attr

                        # Extract metric name and description from args
                        metric_name = None
                        description = None
                        if stmt.value.args:
                            if isinstance(stmt.value.args[0], (ast.Constant, ast.Attribute)):
                                if isinstance(stmt.value.args[0], ast.Constant):
                                    metric_name = stmt.value.args[0].value
                                elif isinstance(stmt.value.args[0], ast.Attribute):
                                    # Handle MetricName.SOMETHING
                                    if isinstance(stmt.value.args[0].value, ast.Name):
                                        metric_name = f"{stmt.value.args[0].value.id}.{stmt.value.args[0].attr}"

                            if len(stmt.value.args) > 1 and isinstance(
                                stmt.value.args[1], ast.Constant
                            ):
                                description = stmt.value.args[1].value

                        self.current_class_info["metrics"].append({
                            "variable": metric_var,
                            "type": metric_type,
                            "name": metric_name,
                            "description": description,
                            "line": stmt.lineno,
                        })

    def _extract_api_calls_from_method(self, node: ast.FunctionDef) -> None:
        """Extract API calls from method decorators and content."""
        # Check for @log_api_call decorators
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                if decorator.func.id == "log_api_call" and decorator.args:
                    if isinstance(decorator.args[0], ast.Constant):
                        api_endpoint = decorator.args[0].value
                        self.current_class_info["api_calls"].append({
                            "endpoint": api_endpoint,
                            "method": node.name,
                            "line": node.lineno,
                        })

        # Look for API calls in method body
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Call):
                # Look for self.api.controller.method or self.parent.api.controller.method
                if isinstance(stmt.func, ast.Attribute):
                    parts = []
                    current = stmt.func
                    while isinstance(current, ast.Attribute):
                        parts.append(current.attr)
                        current = current.value

                    if isinstance(current, ast.Name):
                        parts.append(current.id)

                    # Check for API call patterns
                    if len(parts) >= 3 and parts[-1] == "self" and parts[-2] == "api":
                        controller = parts[-3]
                        method = parts[0]
                        endpoint = f"{controller}.{method}"

                        # Avoid duplicates
                        if not any(
                            call["endpoint"] == endpoint
                            for call in self.current_class_info["api_calls"]
                        ):
                            self.current_class_info["api_calls"].append({
                                "endpoint": endpoint,
                                "method": node.name,
                                "line": getattr(stmt, "lineno", 0),
                            })

    def _extract_sub_collectors_from_init(self, node: ast.FunctionDef) -> None:
        """Extract sub-collector initialization from __init__ method."""
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign):
                # Look for self.something_collector = SomethingCollector(...)
                if (
                    len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Attribute)
                    and isinstance(stmt.targets[0].value, ast.Name)
                    and stmt.targets[0].value.id == "self"
                    and isinstance(stmt.value, ast.Call)
                    and isinstance(stmt.value.func, ast.Name)
                ):
                    var_name = stmt.targets[0].attr
                    collector_class = stmt.value.func.id
                    if "collector" in var_name.lower() or collector_class.endswith("Collector"):
                        self.current_class_info["sub_collectors"].append({
                            "variable": var_name,
                            "class": collector_class,
                            "line": stmt.lineno,
                        })


def scan_for_collectors(root_path: Path, repo_root: Path) -> list[dict[str, Any]]:
    """Scan Python files for collector definitions."""
    all_collectors = []

    collectors_root = root_path / "meraki_dashboard_exporter" / "collectors"
    if not collectors_root.exists():
        print("Could not find collectors directory")
        return []

    print(f"Scanning directory: {collectors_root}")

    for py_file in collectors_root.rglob("*.py"):
        # Skip test files and tool scripts
        if "test" in py_file.parts or py_file.name.startswith("generate_"):
            continue

        try:
            with open(py_file) as f:
                tree = ast.parse(f.read(), filename=str(py_file))

            visitor = CollectorVisitor(py_file, repo_root)
            visitor.visit(tree)

            if visitor.collectors:
                print(
                    f"  Found {len(visitor.collectors)} collectors in {py_file.relative_to(root_path)}"
                )

            all_collectors.extend(visitor.collectors)
        except Exception as e:
            print(f"Error parsing {py_file}: {e}")

    return all_collectors


def resolve_update_tiers(collectors: list[dict[str, Any]]) -> None:
    """Resolve UpdateTier references to actual values."""
    for collector in collectors:
        if collector["update_tier"] and collector["update_tier"] in TIER_MAP:
            collector["resolved_tier"] = TIER_MAP[collector["update_tier"]]
        else:
            collector["resolved_tier"] = collector["update_tier"] or "Managed by parent"


def generate_markdown(collectors: list[dict[str, Any]]) -> str:
    """Generate concise markdown documentation for collectors."""
    lines = ["# Collector Reference", ""]
    lines.append("This page summarizes the collectors that ship with the exporter.")
    lines.append("")
    lines.append(
        "Collectors run on FAST/MEDIUM/SLOW tiers configured via `MERAKI_EXPORTER_UPDATE_INTERVALS__*`."
        " See the Metrics Overview for tier definitions."
    )
    lines.append("")

    total_collectors = len(collectors)
    registered_collectors = [c for c in collectors if c.get("registered")]
    lines.append(f"**Total collector classes:** {total_collectors}")
    lines.append(f"**Auto-registered collectors:** {len(registered_collectors)}")
    lines.append("")

    lines.append("## Main Collectors (auto-registered)")
    lines.append("")
    lines.append("| Collector | Tier | Purpose | Metrics | Notes |")
    lines.append("|-----------|------|---------|---------|-------|")
    for collector in sorted(registered_collectors, key=lambda c: c["name"]):
        description = (
            collector.get("docstring", "").split("\n")[0]
            if collector.get("docstring")
            else "No description"
        )
        metrics_count = len(collector.get("metrics", []))
        notes = COLLECTOR_NOTES.get(collector["name"], "")
        lines.append(
            f"| `{collector['name']}` | {collector.get('resolved_tier', 'Managed by parent')} | "
            f"{description} | {metrics_count} | {notes} |"
        )
    lines.append("")

    lines.append("## Coordinator Relationships")
    lines.append("")
    for collector in sorted(collectors, key=lambda c: c["name"]):
        if not collector["sub_collectors"]:
            continue
        sub_names = ", ".join(sub["class"] for sub in collector["sub_collectors"])
        lines.append(f"- **{collector['name']}** → {sub_names}")
    lines.append("")

    lines.append("## Sub-collector Catalog")
    lines.append("")
    device_subs = [
        c for c in collectors if "/collectors/devices/" in c["file"] and not c.get("registered")
    ]
    network_subs = [
        c
        for c in collectors
        if "/collectors/network_health_collectors/" in c["file"] and not c.get("registered")
    ]
    org_subs = [
        c
        for c in collectors
        if "/collectors/organization_collectors/" in c["file"] and not c.get("registered")
    ]
    other_subs = [
        c
        for c in collectors
        if not c.get("registered")
        and c not in device_subs
        and c not in network_subs
        and c not in org_subs
    ]

    def add_subcollector_section(title: str, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        lines.append(f"### {title}")
        lines.append("")
        for item in sorted(items, key=lambda c: c["name"]):
            description = item.get("docstring", "").split("\n")[0] if item.get("docstring") else ""
            lines.append(f"- `{item['name']}` — {description}")
        lines.append("")

    add_subcollector_section("Device Sub-collectors", device_subs)
    add_subcollector_section("Network Health Sub-collectors", network_subs)
    add_subcollector_section("Organization Sub-collectors", org_subs)
    add_subcollector_section("Other Sub-collectors", other_subs)

    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- Collector enablement is configured in the [Configuration](../config.md) reference."
    )
    lines.append("- Full metric details live in the [Metrics Reference](../metrics/metrics.md).")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    current_path = Path(__file__).resolve()
    repo_root = current_path.parents[1]
    src_path = repo_root / "src"
    if not src_path.exists():
        print("Could not find src/ directory")
        return

    print("Scanning for collectors...")
    collectors = scan_for_collectors(src_path, repo_root)
    print(f"Found {len(collectors)} collector definitions")

    # Resolve update tier references
    print("Resolving update tiers...")
    resolve_update_tiers(collectors)

    # Generate markdown
    print("Generating documentation...")
    markdown = generate_markdown(collectors)

    # Write to docs/collectors/reference.md
    output_file = repo_root / "docs" / "collectors" / "reference.md"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        f.write(markdown)
        f.write("\n")  # Ensure file ends with newline

    print(f"Collector documentation written to {output_file}")


if __name__ == "__main__":
    main()
