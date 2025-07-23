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
                "Client",
                "NetworkHealth",
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
    """Generate enhanced markdown documentation for metrics in mkdocs style."""
    lines = ["# Metrics Reference", ""]
    lines.append(
        "This page provides a comprehensive reference of all Prometheus metrics exposed by the Meraki Dashboard Exporter."
    )
    lines.append("")

    # Add statistics summary
    total_metrics = len(metrics)
    metric_types = {}
    collector_counts = {}

    for metric in metrics:
        metric_type = metric["type"]
        collector = metric["class"] or "Unknown"

        metric_types[metric_type] = metric_types.get(metric_type, 0) + 1
        collector_counts[collector] = collector_counts.get(collector, 0) + 1

    lines.append('!!! summary "Metrics Summary"')
    lines.append(f"    📊 **Total Metrics:** {total_metrics}")
    lines.append(f"    🏗️ **Collectors:** {len(collector_counts)}")
    lines.append(f"    📈 **Gauges:** {metric_types.get('gauge', 0)}")
    lines.append(f"    📊 **Counters:** {metric_types.get('counter', 0)}")
    lines.append(f"    ℹ️ **Info Metrics:** {metric_types.get('info', 0)}")
    lines.append("")

    # Add table of contents
    lines.append("## Overview")
    lines.append("")
    lines.append("The exporter provides metrics across several categories:")
    lines.append("")

    lines.append("| Collector | Metrics | Description |")
    lines.append("|-----------|---------|-------------|")

    collector_descriptions = {
        "AlertsCollector": "🚨 Active alerts by severity, type, and category",
        "ClientsCollector": "👥 Detailed client-level metrics including usage and status",
        "ConfigCollector": "⚙️ Organization security settings and configuration tracking",
        "DeviceCollector": "📱 Device status, performance, and uptime metrics",
        "MSCollector": "🔀 Switch-specific metrics including port status, power, and PoE",
        "MRCollector": "📡 Access point metrics including clients, power, and performance",
        "MTCollector": "🌡️ Environmental sensor metrics from MT devices",
        "MTSensorCollector": "📊 Environmental monitoring from MT sensors",
        "NetworkHealthCollector": "🏥 Network-wide wireless health and performance",
        "OrganizationCollector": "🏢 Organization-level metrics including API usage and licenses",
        "RFHealthCollector": "📶 RF health and channel utilization metrics",
        "ConnectionStatsCollector": "🔗 Wireless connection statistics",
        "DataRatesCollector": "⚡ Network throughput and data rate metrics",
        "BluetoothCollector": "📲 Bluetooth client detection metrics",
        "APIUsageCollector": "🔄 API request tracking and rate limit metrics",
        "LicenseCollector": "📄 License usage and expiration tracking",
        "ClientOverviewCollector": "👁️ Client count and usage overview metrics",
    }

    for collector in sorted(collector_counts.keys()):
        count = collector_counts[collector]
        description = collector_descriptions.get(collector, "Various metrics")
        anchor = collector.lower().replace("collector", "")
        lines.append(f"| [{collector}](#{anchor}) | {count} | {description} |")

    lines.append("")

    # Add Quick Navigation section
    lines.append("## 🧭 Quick Navigation")
    lines.append("")

    # Navigation by metric type
    lines.append("### By Metric Type")
    lines.append("")

    # Group metrics by type for navigation
    metrics_by_type = {}
    for metric in metrics:
        metric_type = metric["type"]
        if metric_type not in metrics_by_type:
            metrics_by_type[metric_type] = []
        metrics_by_type[metric_type].append(metric)

    type_descriptions = {
        "gauge": "📈 **Gauges** - Values that can increase or decrease (current state)",
        "counter": "📊 **Counters** - Cumulative values that only increase",
        "info": "ℹ️ **Info Metrics** - Metadata and configuration information",
    }

    for metric_type in sorted(metrics_by_type.keys()):
        metrics_list = metrics_by_type[metric_type]
        description = type_descriptions.get(metric_type, f"**{metric_type.title()}** metrics")

        lines.append(f'??? abstract "{description} ({len(metrics_list)} metrics)"')
        lines.append("")

        # Sort metrics alphabetically within type
        sorted_metrics = sorted(metrics_list, key=lambda m: m.get("actual_name", m.get("name", "")))

        # Group into columns for better readability
        for i, metric in enumerate(sorted_metrics):
            metric_name = metric.get("actual_name", metric.get("name", "Unknown"))
            collector = metric["class"] or "Unknown"
            anchor = metric_name.lower().replace("_", "-").replace(".", "-")

            if i % 3 == 0:
                if i > 0:
                    lines.append("    ")
                lines.append('    <div class="grid cards" markdown>')
                lines.append("")

            lines.append(f"    - [`{metric_name}`](#{anchor})")
            lines.append("      ---")
            lines.append(f"      {collector}")
            lines.append("")

            if (i + 1) % 3 == 0 or i == len(sorted_metrics) - 1:
                lines.append("    </div>")

        lines.append("")

    # Navigation by collector
    lines.append("### By Collector")
    lines.append("")

    lines.append('=== "Device & Infrastructure"')
    lines.append("")
    device_collectors = [
        "DeviceCollector",
        "MSCollector",
        "MRCollector",
        "MTCollector",
        "MTSensorCollector",
    ]
    for collector in sorted(device_collectors):
        if collector in collector_counts:
            count = collector_counts[collector]
            anchor = collector.lower().replace("collector", "")
            lines.append(f"    - [{collector}](#{anchor}) ({count} metrics)")
    lines.append("")

    lines.append('=== "Network & Health"')
    lines.append("")
    network_collectors = [
        "NetworkHealthCollector",
        "RFHealthCollector",
        "ConnectionStatsCollector",
        "DataRatesCollector",
        "BluetoothCollector",
    ]
    for collector in sorted(network_collectors):
        if collector in collector_counts:
            count = collector_counts[collector]
            anchor = collector.lower().replace("collector", "")
            lines.append(f"    - [{collector}](#{anchor}) ({count} metrics)")
    lines.append("")

    lines.append('=== "Organization & Management"')
    lines.append("")
    org_collectors = [
        "OrganizationCollector",
        "APIUsageCollector",
        "LicenseCollector",
        "ClientOverviewCollector",
        "AlertsCollector",
        "ClientsCollector",
        "ConfigCollector",
    ]
    for collector in sorted(org_collectors):
        if collector in collector_counts:
            count = collector_counts[collector]
            anchor = collector.lower().replace("collector", "")
            lines.append(f"    - [{collector}](#{anchor}) ({count} metrics)")
    lines.append("")

    # Enhanced Metrics by Collector section
    lines.append("## 📋 Metrics by Collector")
    lines.append("")

    # Group metrics by collector class
    by_collector: dict[str, list[dict[str, Any]]] = {}
    for metric in metrics:
        collector = metric["class"] or "Unknown"
        if collector not in by_collector:
            by_collector[collector] = []
        by_collector[collector].append(metric)

    # Sort collectors and add enhanced formatting
    for collector in sorted(by_collector.keys()):
        collector_metrics = by_collector[collector]
        anchor = collector.lower().replace("collector", "")

        lines.append(f"### {collector} {{ #{anchor} }}")
        lines.append("")

        # Add collector info box
        description = collector_descriptions.get(collector, "Various metrics")
        if collector_metrics:
            file_path = collector_metrics[0]["file"]

            lines.append('!!! info "Collector Information"')
            lines.append(f"    **Description:** {description}")
            lines.append(f"    **Source File:** `{file_path}`")
            lines.append(f"    **Metrics Count:** {len(collector_metrics)}")
            lines.append("")

        # Sort metrics by name
        collector_metrics.sort(key=lambda m: m.get("actual_name", m.get("name", "")))

        for i, metric in enumerate(collector_metrics):
            metric_name = metric.get("actual_name", metric.get("name", "Unknown"))
            anchor = metric_name.lower().replace("_", "-").replace(".", "-")

            # Create metric card
            lines.append(f"#### `{metric_name}` {{ #{anchor} }}")
            lines.append("")

            # Metric type badge
            type_badge = {"gauge": "🔢 Gauge", "counter": "📈 Counter", "info": "ℹ️ Info"}
            badge = type_badge.get(metric["type"], metric["type"])
            lines.append(f"**Type:** {badge}")
            lines.append("")

            if "description" in metric:
                lines.append(f"**Description:** {metric['description']}")
                lines.append("")

            if "labels" in metric and metric["labels"]:
                lines.append("**Labels:**")
                lines.append("")
                for label in metric["labels"]:
                    lines.append(f"- `{label}`")
                lines.append("")

            # Technical details in collapsible section
            lines.append('??? example "Technical Details"')
            lines.append("")
            if "constant_name" in metric:
                lines.append(f"    **Constant:** `{metric['constant_name']}`")
                lines.append("")
            lines.append(f"    **Variable:** `self.{metric['variable']}`")
            lines.append(f"    **Source Line:** {metric['line']}")
            lines.append("")

            # Add separator between metrics (except for last one)
            if i < len(collector_metrics) - 1:
                lines.append("---")
                lines.append("")

        lines.append("")

    # Enhanced Complete Metrics Index
    lines.append("## 📖 Complete Metrics Index")
    lines.append("")
    lines.append("All metrics in alphabetical order with quick access:")
    lines.append("")

    # Sort all metrics by name
    all_sorted = sorted(metrics, key=lambda m: m.get("actual_name", m.get("name", "")))

    # Create searchable table
    lines.append("| Metric Name | Type | Collector | Labels | Description |")
    lines.append("|-------------|------|-----------|--------|-------------|")

    for metric in all_sorted:
        name = metric.get("actual_name", metric.get("name", "Unknown"))
        metric_type = metric["type"]
        collector = metric["class"] or "Unknown"
        description = metric.get("description", "").replace("|", "\\|")

        # Create anchor link
        anchor = name.lower().replace("_", "-").replace(".", "-")

        # Format labels
        label_count = len(metric.get("labels", []))
        labels_text = f"{label_count} labels" if label_count > 0 else "No labels"

        # Add type emoji
        type_emoji = {"gauge": "🔢", "counter": "📈", "info": "ℹ️"}.get(metric_type, "")

        lines.append(
            f"| [`{name}`](#{anchor}) | {type_emoji} {metric_type} | {collector} | {labels_text} | {description} |"
        )

    lines.append("")

    # Enhanced notes section
    lines.append("## 📚 Usage Guide")
    lines.append("")

    lines.append('!!! info "Metric Types Explained"')
    lines.append(
        "    - 🔢 **Gauge**: Current value that can go up or down (e.g., current temperature, active connections)"
    )
    lines.append(
        "    - 📈 **Counter**: Cumulative value that only increases (e.g., total requests, total bytes)"
    )
    lines.append(
        "    - ℹ️ **Info**: Metadata with labels but value always 1 (e.g., device information, configuration)"
    )
    lines.append("")

    lines.append('!!! tip "Querying with Labels"')
    lines.append(
        "    All metrics include relevant labels for filtering and aggregation. Use label selectors in your queries:"
    )
    lines.append("    ```promql")
    lines.append("    # Filter by organization")
    lines.append('    meraki_device_up{org_name="Production"}')
    lines.append("")
    lines.append("    # Filter by device type")
    lines.append('    meraki_device_up{device_model=~"MS.*"}')
    lines.append("")
    lines.append("    # Aggregate across multiple labels")
    lines.append("    sum(meraki_device_up) by (org_name, device_model)")
    lines.append("    ```")
    lines.append("")

    lines.append('!!! example "Common Query Patterns"')
    lines.append("    ```promql")
    lines.append("    # Device health overview")
    lines.append("    avg(meraki_device_up) by (org_name)")
    lines.append("")
    lines.append("    # Network utilization")
    lines.append("    rate(meraki_network_traffic_bytes_total[5m])")
    lines.append("")
    lines.append("    # Alert summary")
    lines.append("    sum(meraki_alerts_total) by (severity, type)")
    lines.append("    ```")
    lines.append("")

    lines.append('!!! warning "Performance Considerations"')
    lines.append("    - Use appropriate time ranges for rate() and increase() functions")
    lines.append("    - Consider cardinality when using high-cardinality labels")
    lines.append("    - Monitor query performance in production environments")
    lines.append("")

    lines.append(
        "For more information on using these metrics, see the [Overview](overview.md) page."
    )
    lines.append("")  # Add trailing blank line

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
        f.write("\n")  # Ensure file ends with newline

    print(f"Documentation written to {output_file}")


if __name__ == "__main__":
    main()
