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


class CollectorVisitor(ast.NodeVisitor):
    """AST visitor to find collector definitions and their properties."""

    def __init__(self, filepath: Path) -> None:
        """Initialize visitor."""
        self.filepath = filepath
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
            "file": str(self.filepath.relative_to(Path.cwd())),
            "line": node.lineno,
            "docstring": ast.get_docstring(node),
            "base_classes": [],
            "decorators": [],
            "update_tier": None,
            "metrics": [],
            "api_calls": [],
            "sub_collectors": [],
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


def scan_for_collectors(root_path: Path) -> list[dict[str, Any]]:
    """Scan Python files for collector definitions."""
    all_collectors = []

    print(f"Scanning directory: {root_path}")

    for py_file in root_path.rglob("*.py"):
        # Skip test files and tool scripts
        if "test" in py_file.parts or py_file.name.startswith("generate_"):
            continue

        try:
            with open(py_file) as f:
                tree = ast.parse(f.read(), filename=str(py_file))

            visitor = CollectorVisitor(py_file)
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
    tier_map = {
        "UpdateTier.FAST": "FAST (60s)",
        "UpdateTier.MEDIUM": "MEDIUM (300s)",
        "UpdateTier.SLOW": "SLOW (900s)",
    }

    for collector in collectors:
        if collector["update_tier"] and collector["update_tier"] in tier_map:
            collector["resolved_tier"] = tier_map[collector["update_tier"]]
        else:
            collector["resolved_tier"] = collector["update_tier"] or "Not specified"


def generate_markdown(collectors: list[dict[str, Any]]) -> str:
    """Generate comprehensive markdown documentation for collectors."""
    lines = ["# Collector Reference", ""]
    lines.append(
        "This page provides a comprehensive reference of all metric collectors in the Meraki Dashboard Exporter."
    )
    lines.append("")

    # Add statistics summary
    total_collectors = len(collectors)
    registered_collectors = sum(
        1 for c in collectors if any(d["name"] == "register_collector" for d in c["decorators"])
    )
    sub_collectors = sum(1 for c in collectors if c["sub_collectors"])

    lines.append('!!! summary "Collector Overview"')
    lines.append(f"    🏗️ **Total Collectors:** {total_collectors}")
    lines.append(f"    📋 **Registered Collectors:** {registered_collectors}")
    lines.append(f"    🔗 **Coordinators with Sub-collectors:** {sub_collectors}")
    lines.append("")

    # Add architecture overview
    lines.append("## 🏛️ Architecture Overview")
    lines.append("")
    lines.append("The collector system is organized in a hierarchical pattern:")
    lines.append("")
    lines.append("### Update Tiers")
    lines.append("")
    lines.append("Collectors are organized into three update tiers based on data volatility:")
    lines.append("")
    lines.append("| Tier | Interval | Purpose | Examples |")
    lines.append("|------|----------|---------|----------|")
    lines.append(
        "| 🚀 **FAST** | 60s | Real-time status, critical metrics | Device status, alerts, sensor readings |"
    )
    lines.append(
        "| ⚡ **MEDIUM** | 300s | Regular metrics, performance data | Device metrics, network health, client data |"
    )
    lines.append(
        "| 🐌 **SLOW** | 900s | Infrequent data, configuration | License usage, organization summaries |"
    )
    lines.append("")

    lines.append("### Collector Types")
    lines.append("")
    lines.append("| Type | Description | Registration |")
    lines.append("|------|-------------|--------------|")
    lines.append(
        "| **Main Collectors** | Top-level collectors with `@register_collector` | Automatic |"
    )
    lines.append("| **Coordinator Collectors** | Manage multiple sub-collectors | Automatic |")
    lines.append("| **Sub-collectors** | Specialized collectors for specific metrics | Manual |")
    lines.append("| **Device Collectors** | Device-type specific (MR, MS, MX, etc.) | Manual |")
    lines.append("")

    # Navigation by tier
    lines.append("## 🧭 Quick Navigation")
    lines.append("")

    # Group by update tier
    by_tier: dict[str, list[dict[str, Any]]] = {
        "FAST": [],
        "MEDIUM": [],
        "SLOW": [],
        "Not specified": [],
    }
    for collector in collectors:
        tier = collector.get("resolved_tier", "Not specified")
        if "FAST" in tier:
            by_tier["FAST"].append(collector)
        elif "MEDIUM" in tier:
            by_tier["MEDIUM"].append(collector)
        elif "SLOW" in tier:
            by_tier["SLOW"].append(collector)
        else:
            by_tier["Not specified"].append(collector)

    lines.append("### By Update Tier")
    lines.append("")

    for tier_name, tier_collectors in by_tier.items():
        if not tier_collectors:
            continue

        tier_emoji = {"FAST": "🚀", "MEDIUM": "⚡", "SLOW": "🐌", "Not specified": "❓"}[tier_name]
        lines.append(
            f'??? abstract "{tier_emoji} {tier_name} Tier ({len(tier_collectors)} collectors)"'
        )
        lines.append("")

        for collector in sorted(tier_collectors, key=lambda c: c["name"]):
            name = collector["name"]
            description = (
                collector.get("docstring", "").split("\n")[0]
                if collector.get("docstring")
                else "No description"
            )
            if len(description) > 80:
                description = description[:77] + "..."
            anchor = name.lower().replace("collector", "")
            lines.append(f"    - [`{name}`](#{anchor}): {description}")
        lines.append("")

    # Group by type
    lines.append("### By Type")
    lines.append("")

    # Categorize collectors
    main_collectors = [
        c for c in collectors if any(d["name"] == "register_collector" for d in c["decorators"])
    ]
    device_collectors = [
        c for c in collectors if any("BaseDeviceCollector" in base for base in c["base_classes"])
    ]
    sub_collectors_list = [
        c
        for c in collectors
        if not any(d["name"] == "register_collector" for d in c["decorators"])
        and not any("BaseDeviceCollector" in base for base in c["base_classes"])
    ]

    lines.append('=== "Main Collectors"')
    lines.append("")
    lines.append("    Auto-registered collectors that run on scheduled intervals:")
    lines.append("")
    for collector in sorted(main_collectors, key=lambda c: c["name"]):
        tier = collector.get("resolved_tier", "Not specified")
        anchor = collector["name"].lower().replace("collector", "")
        lines.append(f"    - [`{collector['name']}`](#{anchor}) - {tier}")
    lines.append("")

    lines.append('=== "Device Collectors"')
    lines.append("")
    lines.append("    Device-type specific collectors (MR, MS, MX, MT, MG, MV):")
    lines.append("")
    for collector in sorted(device_collectors, key=lambda c: c["name"]):
        anchor = collector["name"].lower().replace("collector", "")
        description = (
            collector.get("docstring", "").split("\n")[0] if collector.get("docstring") else ""
        )
        lines.append(f"    - [`{collector['name']}`](#{anchor}): {description}")
    lines.append("")

    lines.append('=== "Sub-collectors"')
    lines.append("")
    lines.append("    Specialized collectors managed by coordinator collectors:")
    lines.append("")
    for collector in sorted(sub_collectors_list, key=lambda c: c["name"]):
        anchor = collector["name"].lower().replace("collector", "")
        description = (
            collector.get("docstring", "").split("\n")[0] if collector.get("docstring") else ""
        )
        lines.append(f"    - [`{collector['name']}`](#{anchor}): {description}")
    lines.append("")

    # Detailed collector documentation
    lines.append("## 📋 Collector Details")
    lines.append("")

    # Sort collectors by name for consistent ordering
    for collector in sorted(collectors, key=lambda c: c["name"]):
        name = collector["name"]
        anchor = name.lower().replace("collector", "")

        lines.append(f"### {name} {{ #{anchor} }}")
        lines.append("")

        # Basic info box
        lines.append('!!! info "Collector Information"')
        if collector.get("docstring"):
            # Clean up docstring
            docstring = collector["docstring"].strip()
            first_line = docstring.split("\n")[0]
            lines.append(f"    **Purpose:** {first_line}")
        lines.append(f"    **Source File:** `{collector['file']}`")
        lines.append(f"    **Update Tier:** {collector.get('resolved_tier', 'Not specified')}")
        if collector["base_classes"]:
            lines.append(f"    **Inherits From:** {', '.join(collector['base_classes'])}")
        lines.append("")

        # Metrics section
        if collector["metrics"]:
            lines.append("#### 📊 Metrics Collected")
            lines.append("")
            lines.append("| Metric Variable | Type | Name | Description |")
            lines.append("|-----------------|------|------|-------------|")
            for metric in collector["metrics"]:
                name = metric.get("name", "Unknown")
                description = metric.get("description", "").replace("|", "\\|")
                lines.append(
                    f"| `{metric['variable']}` | {metric['type']} | `{name}` | {description} |"
                )
            lines.append("")

        # API calls section
        if collector["api_calls"]:
            lines.append("#### 🔌 API Endpoints Used")
            lines.append("")
            unique_endpoints = {}
            for call in collector["api_calls"]:
                endpoint = call["endpoint"]
                if endpoint not in unique_endpoints:
                    unique_endpoints[endpoint] = call["method"]

            lines.append("| Endpoint | Used In Method |")
            lines.append("|----------|----------------|")
            for endpoint, method in sorted(unique_endpoints.items()):
                lines.append(f"| `{endpoint}` | `{method}()` |")
            lines.append("")

        # Sub-collectors section
        if collector["sub_collectors"]:
            lines.append("#### 🔗 Sub-collectors")
            lines.append("")
            lines.append("This coordinator manages the following sub-collectors:")
            lines.append("")
            for sub in collector["sub_collectors"]:
                sub_anchor = sub["class"].lower().replace("collector", "")
                lines.append(f"- [`{sub['class']}`](#{sub_anchor}) (as `self.{sub['variable']}`)")
            lines.append("")

        # Technical details
        lines.append('??? example "Technical Details"')
        lines.append("")
        if collector["decorators"]:
            lines.append("    **Decorators:**")
            for decorator in collector["decorators"]:
                if decorator["args"]:
                    args_str = ", ".join(str(arg) for arg in decorator["args"])
                    lines.append(f"    - `@{decorator['name']}({args_str})`")
                else:
                    lines.append(f"    - `@{decorator['name']}`")
            lines.append("")

        lines.append(f"    **Defined at:** Line {collector['line']}")
        if collector["metrics"]:
            lines.append(f"    **Metrics Count:** {len(collector['metrics'])}")
        if collector["api_calls"]:
            unique_apis = len({call["endpoint"] for call in collector["api_calls"]})
            lines.append(f"    **API Endpoints:** {unique_apis}")
        lines.append("")

        lines.append("---")
        lines.append("")

    # Add usage guide
    lines.append("## 📚 Usage Guide")
    lines.append("")

    lines.append('!!! tip "Understanding Collector Hierarchy"')
    lines.append(
        "    - **Main Collectors** are registered with `@register_collector()` and run automatically"
    )
    lines.append(
        "    - **Coordinator Collectors** manage multiple sub-collectors for related metrics"
    )
    lines.append("    - **Device Collectors** are specific to device types (MR, MS, MX, etc.)")
    lines.append(
        "    - **Sub-collectors** are manually registered and called by their parent coordinators"
    )
    lines.append("")

    lines.append('!!! info "Update Tier Strategy"')
    lines.append(
        "    - **FAST (60s):** Critical metrics that change frequently (device status, alerts)"
    )
    lines.append(
        "    - **MEDIUM (300s):** Regular metrics with moderate change frequency (performance data)"
    )
    lines.append(
        "    - **SLOW (900s):** Stable metrics that change infrequently (configuration, licenses)"
    )
    lines.append("")

    lines.append('!!! example "Adding a New Collector"')
    lines.append("    ```python")
    lines.append("    from ..core.collector import register_collector, MetricCollector, UpdateTier")
    lines.append("    from ..core.constants.metrics_constants import MetricName")
    lines.append("    from ..core.error_handling import with_error_handling")
    lines.append("")
    lines.append("    @register_collector(UpdateTier.MEDIUM)")
    lines.append("    class MyCollector(MetricCollector):")
    lines.append('        """My custom collector for specific metrics."""')
    lines.append("")
    lines.append("        def _initialize_metrics(self) -> None:")
    lines.append("            self.my_metric = self._create_gauge(")
    lines.append("                MetricName.MY_METRIC,")
    lines.append('                "Description of my metric"')
    lines.append("            )")
    lines.append("")
    lines.append("        @with_error_handling('Collect my data')")
    lines.append("        async def _collect_impl(self) -> None:")
    lines.append("            # Collection logic here")
    lines.append("            pass")
    lines.append("    ```")
    lines.append("")

    lines.append(
        "For more information on metrics, see the [Metrics Reference](metrics/metrics.md)."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    # Find project root (where src/ is)
    current_path = Path.cwd()
    src_path = current_path / "src"
    if not src_path.exists():
        # Try parent directory
        src_path = current_path.parent / "src"
        if not src_path.exists():
            print("Could not find src/ directory")
            return

    print("Scanning for collectors...")
    collectors = scan_for_collectors(src_path)
    print(f"Found {len(collectors)} collector definitions")

    # Resolve update tier references
    print("Resolving update tiers...")
    resolve_update_tiers(collectors)

    # Generate markdown
    print("Generating documentation...")
    markdown = generate_markdown(collectors)

    # Write to docs/collectors.md
    output_file = Path("docs/collectors.md")
    with open(output_file, "w") as f:
        f.write(markdown)
        f.write("\n")  # Ensure file ends with newline

    print(f"Collector documentation written to {output_file}")


if __name__ == "__main__":
    main()
