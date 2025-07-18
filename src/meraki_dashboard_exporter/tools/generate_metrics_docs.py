#!/usr/bin/env python3
"""Generate documentation for all metrics defined in the exporter.

This script scans the codebase to find all metric definitions and generates
a markdown document listing them with their descriptions, labels, and locations.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


class MetricVisitor(ast.NodeVisitor):
    """AST visitor to find metric definitions."""

    def __init__(self, filepath: Path) -> None:
        """Initialize visitor."""
        self.filepath = filepath
        self.metrics: list[dict[str, Any]] = []
        self.current_class: str | None = None
        self.in_initialize_metrics = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition."""
        old_in_init = self.in_initialize_metrics
        if node.name in ("_initialize_metrics", "__init__"):
            self.in_initialize_metrics = True
        self.generic_visit(node)
        self.in_initialize_metrics = old_in_init

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit assignment to find metric definitions."""
        if not self.in_initialize_metrics:
            return

        # Check if this is a metric assignment (self._something = self._create_... or self.parent._create_...)
        if (  # noqa: PLR1702
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Attribute)
            and isinstance(node.targets[0].value, ast.Name)
            and node.targets[0].value.id == "self"
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
        ):
            # Handle both self._create_... and self.parent._create_...
            if (
                isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id == "self"
                and node.value.func.attr.startswith("_create_")
            ):
                # Direct metric creation: self._create_gauge(...)
                metric_type = node.value.func.attr.replace("_create_", "")
                metric_name_attr = node.targets[0].attr
            elif (
                isinstance(node.value.func.value, ast.Attribute)
                and isinstance(node.value.func.value.value, ast.Name)
                and node.value.func.value.value.id == "self"
                and node.value.func.value.attr == "parent"
                and node.value.func.attr.startswith("_create_")
            ):
                # Parent metric creation: self.parent._create_gauge(...)
                metric_type = node.value.func.attr.replace("_create_", "")
                metric_name_attr = node.targets[0].attr
            else:
                self.generic_visit(node)
                return

            # Extract arguments
            args_dict: dict[str, Any] = {}
            if node.value.args:
                # First positional arg is usually the metric name
                if isinstance(node.value.args[0], ast.Constant):
                    args_dict["name"] = node.value.args[0].value
                elif isinstance(node.value.args[0], ast.Attribute):
                    # Handle various MetricName patterns: MetricName.X, OrgMetricName.X, MRMetricName.X, etc.
                    if isinstance(node.value.args[0].value, ast.Name):
                        metric_class = node.value.args[0].value.id
                        metric_attr = node.value.args[0].attr
                        args_dict["name"] = f"{metric_class}.{metric_attr}"

                # Second positional arg is usually the description
                if len(node.value.args) > 1 and isinstance(node.value.args[1], ast.Constant):
                    args_dict["description"] = node.value.args[1].value

            # Extract keyword arguments
            for keyword in node.value.keywords:
                if keyword.arg == "labelnames" and isinstance(keyword.value, ast.List):
                    labels = []
                    for elt in keyword.value.elts:
                        if isinstance(elt, ast.Constant):
                            labels.append(elt.value)
                        elif isinstance(elt, ast.Attribute):
                            # Handle LabelName.SOMETHING
                            if isinstance(elt.value, ast.Name) and elt.value.id == "LabelName":
                                labels.append(f"LabelName.{elt.attr}")
                            elif hasattr(elt.value, "id"):
                                labels.append(f"{elt.value.id}.{elt.attr}")
                            else:
                                labels.append(str(elt.attr))
                    args_dict["labels"] = labels

            self.metrics.append({
                "type": metric_type,
                "variable": metric_name_attr,
                "class": self.current_class,
                "file": str(self.filepath.relative_to(Path.cwd())),
                "line": node.lineno,
                **args_dict,
            })

        self.generic_visit(node)


def scan_for_metrics(root_path: Path) -> list[dict[str, Any]]:
    """Scan Python files for metric definitions."""
    all_metrics = []

    print(f"Scanning directory: {root_path}")

    for py_file in root_path.rglob("*.py"):
        # Skip test files and this script
        if "test" in py_file.parts or py_file.name == "generate_metrics_docs.py":
            continue

        try:
            with open(py_file) as f:
                tree = ast.parse(f.read(), filename=str(py_file))

            visitor = MetricVisitor(py_file)
            visitor.visit(tree)

            if visitor.metrics:
                print(f"  Found {len(visitor.metrics)} metrics in {py_file.relative_to(root_path)}")

            all_metrics.extend(visitor.metrics)
        except Exception as e:
            print(f"Error parsing {py_file}: {e}")

    return all_metrics


def resolve_metric_names(metrics: list[dict[str, Any]], constants_dir: Path) -> None:
    """Resolve various MetricName classes to actual string values."""
    # Parse all constants files to get metric name values
    metric_name_map = {}

    # Look for all metric constant files
    for constants_file in constants_dir.glob("*_constants.py"):
        try:
            with open(constants_file) as f:
                content = f.read()

            # Find all StrEnum classes that end with "MetricName"
            for class_match in re.finditer(
                r"class (\w*MetricName)\(StrEnum\):(.*?)(?=class|\Z)", content, re.DOTALL
            ):
                class_name, class_body = class_match.groups()
                # Find all constant definitions
                for const_match in re.finditer(r'(\w+)\s*=\s*"([^"]+)"', class_body):
                    const_name, const_value = const_match.groups()
                    metric_name_map[f"{class_name}.{const_name}"] = const_value

        except Exception as e:
            print(f"Error parsing constants file {constants_file}: {e}")

    print(f"Resolved {len(metric_name_map)} metric name constants")

    # Resolve metric names
    for metric in metrics:
        if "name" in metric:
            if metric["name"] in metric_name_map:
                metric["actual_name"] = metric_name_map[metric["name"]]
                metric["constant_name"] = metric["name"]
            elif not metric["name"].startswith((
                "Org",
                "Device",
                "Network",
                "MS",
                "MR",
                "MV",
                "MT",
                "Alert",
                "Config",
            )):
                # If it's already a string constant, use it directly
                metric["actual_name"] = metric["name"]
            else:
                metric["actual_name"] = metric["name"]  # Couldn't resolve
        else:
            metric["actual_name"] = "Unknown"

    # Resolve label names
    for metric in metrics:
        if "labels" in metric:
            resolved_labels = []
            for label in metric["labels"]:
                if label.startswith("LabelName."):
                    # Keep the constant name for documentation
                    resolved_labels.append(label)
                else:
                    resolved_labels.append(label)
            metric["labels"] = resolved_labels


def generate_markdown(metrics: list[dict[str, Any]]) -> str:
    """Generate markdown documentation for metrics in mkdocs style."""
    lines = ["# Metrics Reference", ""]
    lines.append(
        "This page provides a comprehensive reference of all Prometheus metrics exposed by the Meraki Dashboard Exporter."
    )
    lines.append("")

    # Add table of contents
    lines.append("## Overview")
    lines.append("")
    lines.append("The exporter provides metrics across several categories:")
    lines.append("")

    # Count metrics by collector
    collector_counts: dict[str, int] = {}
    for metric in metrics:
        collector = metric["class"] or "Unknown"
        collector_counts[collector] = collector_counts.get(collector, 0) + 1

    lines.append("| Collector | Metrics | Description |")
    lines.append("|-----------|---------|-------------|")

    collector_descriptions = {
        "AlertsCollector": "Active alerts by severity, type, and category",
        "ConfigCollector": "Organization security settings and configuration tracking",
        "DeviceCollector": "Device status, performance, and uptime metrics",
        "MSCollector": "Switch-specific metrics including port status, power, and PoE",
        "MRCollector": "Access point metrics including clients, power, and performance",
        "MTCollector": "Environmental sensor metrics from MT devices",
        "MTSensorCollector": "Environmental monitoring from MT sensors",
        "NetworkHealthCollector": "Network-wide wireless health and performance",
        "OrganizationCollector": "Organization-level metrics including API usage and licenses",
        "RFHealthCollector": "RF health and channel utilization metrics",
        "ConnectionStatsCollector": "Wireless connection statistics",
        "DataRatesCollector": "Network throughput and data rate metrics",
        "BluetoothCollector": "Bluetooth client detection metrics",
        "APIUsageCollector": "API request tracking and rate limit metrics",
        "LicenseCollector": "License usage and expiration tracking",
        "ClientOverviewCollector": "Client count and usage overview metrics",
    }

    for collector in sorted(collector_counts.keys()):
        count = collector_counts[collector]
        description = collector_descriptions.get(collector, "Various metrics")
        lines.append(f"| {collector} | {count} | {description} |")

    lines.append("")

    # Add metrics by collector
    lines.append("## Metrics by Collector")
    lines.append("")

    # Group metrics by collector class
    by_collector: dict[str, list[dict[str, Any]]] = {}
    for metric in metrics:
        collector = metric["class"] or "Unknown"
        if collector not in by_collector:
            by_collector[collector] = []
        by_collector[collector].append(metric)

    # Sort collectors
    for collector in sorted(by_collector.keys()):
        collector_metrics = by_collector[collector]
        lines.append(f"### {collector}")
        lines.append("")

        # Find the file for this collector
        if collector_metrics:
            file_path = collector_metrics[0]["file"]
            lines.append(f"**Source:** `{file_path}`")
            lines.append("")

        # Sort metrics by name
        collector_metrics.sort(key=lambda m: m.get("actual_name", m.get("name", "")))

        for metric in collector_metrics:
            metric_name = metric.get("actual_name", metric.get("name", "Unknown"))
            lines.append(f"#### `{metric_name}`")
            lines.append("")

            if "description" in metric:
                lines.append(f"**Description:** {metric['description']}")
                lines.append("")

            lines.append(f"**Type:** {metric['type']}")
            lines.append("")

            if "labels" in metric:
                labels_list = ", ".join(f"`{label}`" for label in metric["labels"])
                lines.append(f"**Labels:** {labels_list}")
                lines.append("")

            if "constant_name" in metric:
                lines.append(f"**Constant:** `{metric['constant_name']}`")
                lines.append("")

            lines.append(f"**Variable:** `self.{metric['variable']}` (line {metric['line']})")
            lines.append("")

    lines.append("## Complete Metrics Index")
    lines.append("")
    lines.append("All metrics in alphabetical order:")
    lines.append("")

    # Sort all metrics by name
    all_sorted = sorted(metrics, key=lambda m: m.get("actual_name", m.get("name", "")))

    lines.append("| Metric Name | Type | Collector | Description |")
    lines.append("|-------------|------|-----------|-------------|")

    for metric in all_sorted:
        name = metric.get("actual_name", metric.get("name", "Unknown"))
        metric_type = metric["type"]
        collector = metric["class"] or "Unknown"
        description = metric.get("description", "").replace("|", "\\|")

        lines.append(f"| `{name}` | {metric_type} | {collector} | {description} |")

    lines.append("")

    # Add notes section
    lines.append("## Notes")
    lines.append("")
    lines.append('!!! info "Metric Types"')
    lines.append("    - **Gauge**: Current value that can go up or down")
    lines.append("    - **Counter**: Cumulative value that only increases")
    lines.append("    - **Info**: Metadata with labels but value always 1")
    lines.append("")
    lines.append('!!! tip "Label Usage"')
    lines.append(
        "    All metrics include relevant labels for filtering and aggregation. Use label selectors in your queries:"
    )
    lines.append("    ```promql")
    lines.append("    # Filter by organization")
    lines.append('    meraki_device_up{org_name="Production"}')
    lines.append("    ")
    lines.append("    # Filter by device type")
    lines.append('    meraki_device_up{device_model=~"MS.*"}')
    lines.append("    ```")
    lines.append("")
    lines.append(
        "For more information on using these metrics, see the [Overview](overview.md) page."
    )

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

    print("Scanning for metrics...")
    metrics = scan_for_metrics(src_path)
    print(f"Found {len(metrics)} metric definitions")

    # Resolve metric name constants
    constants_dir = src_path / "meraki_dashboard_exporter" / "core" / "constants"
    if constants_dir.exists():
        print("Resolving metric name constants...")
        resolve_metric_names(metrics, constants_dir)

    # Generate markdown
    print("Generating documentation...")
    markdown = generate_markdown(metrics)

    # Write to docs/metrics/metrics.md
    output_file = Path("docs/metrics/metrics.md")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        f.write(markdown)

    print(f"Documentation written to {output_file}")


if __name__ == "__main__":
    main()
