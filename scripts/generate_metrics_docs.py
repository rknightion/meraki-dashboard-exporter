#!/usr/bin/env python3
"""Generate documentation for all metrics defined in the exporter.

This script scans the codebase to find Prometheus metric definitions and
produces a concise reference in docs/metrics/metrics.md.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PROM_METRIC_TYPES = {
    "Gauge": "gauge",
    "Counter": "counter",
    "Histogram": "histogram",
    "Info": "info",
}

EXCLUDED_CLASS_NAMES = {
    "SpanMetricsAggregator",  # Not instantiated yet
    "CircuitBreaker",  # Not wired in
}

EXCLUDED_FILES = {
    "async_utils.py",  # CircuitBreaker metrics are not wired in
}

CONDITIONAL_NOTES = {
    "ClientsCollector": "Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true",
    "WebhookHandler": "Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true",
}

INTERNAL_OWNERS = {
    "CollectorManager",
}


@dataclass
class MetricDefinition:
    """Captured metric definition."""

    name: str
    metric_type: str
    description: str
    labels: list[str]
    owner: str
    category: str
    file: str
    line: int
    notes: str | None


def find_repo_root(start_path: Path) -> Path:
    """Find the repository root by walking upwards."""
    for candidate in [start_path, *start_path.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    raise FileNotFoundError("Could not locate repository root (pyproject.toml + src)")


def read_text(path: Path) -> str:
    """Read a file as UTF-8 text."""
    return path.read_text(encoding="utf-8")


def parse_metric_constants(constants_dir: Path) -> dict[str, str]:
    """Parse metric name constants from *_constants.py files using AST."""
    metric_name_map: dict[str, str] = {}

    for constants_file in constants_dir.glob("*_constants.py"):
        tree = ast.parse(read_text(constants_file), filename=str(constants_file))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("MetricName"):
                continue
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                    target = stmt.targets[0]
                    if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Constant):
                        if isinstance(stmt.value.value, str):
                            metric_name_map[f"{node.name}.{target.id}"] = stmt.value.value
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                        metric_name_map[f"{node.name}.{stmt.target.id}"] = stmt.value.value

    return metric_name_map


def parse_label_constants(metrics_file: Path) -> dict[str, str]:
    """Parse LabelName constants from core/metrics.py using AST."""
    label_map: dict[str, str] = {}
    tree = ast.parse(read_text(metrics_file), filename=str(metrics_file))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "LabelName":
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Constant):
                    if isinstance(stmt.value.value, str):
                        label_map[f"LabelName.{target.id}"] = stmt.value.value
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    label_map[f"LabelName.{stmt.target.id}"] = stmt.value.value
    return label_map


def flatten_attribute(node: ast.Attribute) -> list[str]:
    """Flatten an attribute chain into parts."""
    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return list(reversed(parts))


def attribute_to_constant(node: ast.Attribute) -> str | None:
    """Convert an attribute node to a constant name like Class.NAME."""
    parts = flatten_attribute(node)
    if not parts:
        return None
    if parts[-1] == "value":
        parts = parts[:-1]
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return None


def resolve_name_expr(node: ast.AST, metric_name_map: dict[str, str]) -> str | None:
    """Resolve metric name expressions into actual metric names."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Attribute):
        constant_name = attribute_to_constant(node)
        if constant_name and constant_name in metric_name_map:
            return metric_name_map[constant_name]
        if constant_name:
            return constant_name
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = resolve_name_expr(node.left, metric_name_map)
        right = resolve_name_expr(node.right, metric_name_map)
        if left is not None and right is not None:
            return f"{left}{right}"
    return None


def resolve_label_expr(node: ast.AST, label_map: dict[str, str]) -> str | None:
    """Resolve label expressions into actual label names."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Attribute):
        constant_name = attribute_to_constant(node)
        if constant_name and constant_name in label_map:
            return label_map[constant_name]
        if constant_name:
            return constant_name
    return None


def parse_label_list(node: ast.AST, label_map: dict[str, str]) -> list[str]:
    """Parse a literal list/tuple/set of labels."""
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return []
    labels: list[str] = []
    for elt in node.elts:
        label = resolve_label_expr(elt, label_map)
        if label:
            labels.append(label)
    return labels


def extract_description(call: ast.Call) -> str:
    """Extract a description string from a call."""
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        if isinstance(call.args[1].value, str):
            return call.args[1].value

    for keyword in call.keywords:
        if keyword.arg in {"documentation", "help", "description"}:
            if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                return keyword.value.value

    return ""


def extract_labels(
    call: ast.Call, label_map: dict[str, str], label_vars: dict[str, list[str]] | None = None
) -> list[str]:
    """Extract label names from a call's labelnames keyword."""
    for keyword in call.keywords:
        if keyword.arg != "labelnames":
            continue
        if isinstance(keyword.value, (ast.List, ast.Tuple, ast.Set)):
            return parse_label_list(keyword.value, label_map)
        if isinstance(keyword.value, ast.Name) and label_vars is not None:
            return label_vars.get(keyword.value.id, [])
    return []


def categorize_metric(owner: str, file_path: str) -> str:
    """Decide whether a metric is collector or internal."""
    if owner in INTERNAL_OWNERS:
        return "Internal"
    return "Collector" if "/collectors/" in file_path else "Internal"


class CreateMetricVisitor(ast.NodeVisitor):
    """Find metrics created via _create_* helpers."""

    def __init__(
        self,
        filepath: Path,
        repo_root: Path,
        metric_name_map: dict[str, str],
        label_map: dict[str, str],
    ) -> None:
        self.filepath = filepath
        self.repo_root = repo_root
        self.metric_name_map = metric_name_map
        self.label_map = label_map
        self.current_class: str | None = None
        self.metrics: list[MetricDefinition] = []
        self._label_vars_stack: list[dict[str, list[str]]] = []

    def _label_vars(self) -> dict[str, list[str]]:
        if self._label_vars_stack:
            return self._label_vars_stack[-1]
        return {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name in EXCLUDED_CLASS_NAMES:
            return
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._label_vars_stack.append({})
        self.generic_visit(node)
        self._label_vars_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._label_vars_stack.append({})
        self.generic_visit(node)
        self._label_vars_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            labels = parse_label_list(node.value, self.label_map)
            if labels:
                self._label_vars()[node.targets[0].id] = labels

        if not self.current_class:
            return
        if not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Attribute):
            return

        func = node.value.func
        if not func.attr.startswith("_create_"):
            return

        if not (
            isinstance(func.value, ast.Name)
            and func.value.id == "self"
            or (
                isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "self"
                and func.value.attr == "parent"
            )
        ):
            return

        metric_type = func.attr.replace("_create_", "")
        name_expr = node.value.args[0] if node.value.args else None
        if not name_expr:
            return

        metric_name = resolve_name_expr(name_expr, self.metric_name_map)
        if not metric_name:
            return

        description = extract_description(node.value)
        labels = extract_labels(node.value, self.label_map, self._label_vars())

        owner = self.current_class
        file_path = str(self.filepath.relative_to(self.repo_root))
        category = categorize_metric(owner, file_path)
        notes = CONDITIONAL_NOTES.get(owner)

        self.metrics.append(
            MetricDefinition(
                name=metric_name,
                metric_type=metric_type,
                description=description,
                labels=labels,
                owner=owner,
                category=category,
                file=file_path,
                line=node.lineno,
                notes=notes,
            )
        )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and isinstance(node.target, ast.Name):
            labels = parse_label_list(node.value, self.label_map)
            if labels:
                self._label_vars()[node.target.id] = labels
        if not isinstance(node.value, ast.Call):
            return
        assign = ast.Assign(targets=[node.target], value=node.value)
        self.visit_Assign(assign)


class PrometheusMetricVisitor(ast.NodeVisitor):
    """Find metrics created directly via Prometheus constructors."""

    def __init__(
        self,
        filepath: Path,
        repo_root: Path,
        metric_name_map: dict[str, str],
        label_map: dict[str, str],
    ) -> None:
        self.filepath = filepath
        self.repo_root = repo_root
        self.metric_name_map = metric_name_map
        self.label_map = label_map
        self.current_class: str | None = None
        self.metrics: list[MetricDefinition] = []
        self._label_vars_stack: list[dict[str, list[str]]] = []

    def _label_vars(self) -> dict[str, list[str]]:
        if self._label_vars_stack:
            return self._label_vars_stack[-1]
        return {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name in EXCLUDED_CLASS_NAMES:
            return
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._label_vars_stack.append({})
        self.generic_visit(node)
        self._label_vars_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._label_vars_stack.append({})
        self.generic_visit(node)
        self._label_vars_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            labels = parse_label_list(node.value, self.label_map)
            if labels:
                self._label_vars()[node.targets[0].id] = labels

        if not isinstance(node.value, ast.Call):
            return

        func_name = None
        if isinstance(node.value.func, ast.Name):
            func_name = node.value.func.id
        elif isinstance(node.value.func, ast.Attribute):
            func_name = node.value.func.attr

        if func_name not in PROM_METRIC_TYPES:
            return

        name_expr = node.value.args[0] if node.value.args else None
        if not name_expr:
            return

        metric_name = resolve_name_expr(name_expr, self.metric_name_map)
        if not metric_name:
            return

        description = extract_description(node.value)
        labels = extract_labels(node.value, self.label_map, self._label_vars())
        metric_type = PROM_METRIC_TYPES[func_name]

        owner = self.current_class or self.filepath.stem
        file_path = str(self.filepath.relative_to(self.repo_root))
        category = categorize_metric(owner, file_path)
        notes = CONDITIONAL_NOTES.get(owner)

        self.metrics.append(
            MetricDefinition(
                name=metric_name,
                metric_type=metric_type,
                description=description,
                labels=labels,
                owner=owner,
                category=category,
                file=file_path,
                line=node.lineno,
                notes=notes,
            )
        )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and isinstance(node.target, ast.Name):
            labels = parse_label_list(node.value, self.label_map)
            if labels:
                self._label_vars()[node.target.id] = labels
        if not isinstance(node.value, ast.Call):
            return
        assign = ast.Assign(targets=[node.target], value=node.value)
        self.visit_Assign(assign)


def scan_for_metrics(
    src_path: Path,
    repo_root: Path,
    metric_name_map: dict[str, str],
    label_map: dict[str, str],
) -> list[MetricDefinition]:
    """Scan Python files for metric definitions."""
    all_metrics: list[MetricDefinition] = []

    print(f"Scanning directory: {src_path}")

    for py_file in src_path.rglob("*.py"):
        if py_file.name == "generate_metrics_docs.py":
            continue
        if any(part in {"tests", "test", "__pycache__"} for part in py_file.parts):
            continue
        if py_file.name in EXCLUDED_FILES:
            continue

        try:
            tree = ast.parse(read_text(py_file), filename=str(py_file))
            create_visitor = CreateMetricVisitor(py_file, repo_root, metric_name_map, label_map)
            create_visitor.visit(tree)

            direct_visitor = PrometheusMetricVisitor(py_file, repo_root, metric_name_map, label_map)
            direct_visitor.visit(tree)

            file_metrics = create_visitor.metrics + direct_visitor.metrics
            if file_metrics:
                print(f"  Found {len(file_metrics)} metrics in {py_file.relative_to(src_path)}")
            all_metrics.extend(file_metrics)
        except Exception as exc:
            print(f"Error parsing {py_file}: {exc}")

    # Deduplicate by name + owner + type
    deduped: list[MetricDefinition] = []
    seen: set[tuple[str, str, str]] = set()
    for metric in all_metrics:
        key = (metric.name, metric.owner, metric.metric_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(metric)

    return deduped


def generate_markdown(metrics: list[MetricDefinition]) -> str:
    """Generate concise markdown documentation for metrics."""
    lines: list[str] = ["# Metrics Reference", ""]
    lines.append(
        "This page provides a reference of Prometheus metrics exposed by the Meraki Dashboard Exporter."
    )
    lines.append("Some metrics are conditional (clients or webhooks); notes are shown where relevant.")
    lines.append("")

    metric_types: dict[str, int] = {}
    for metric in metrics:
        metric_types[metric.metric_type] = metric_types.get(metric.metric_type, 0) + 1

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total metrics:** {len(metrics)}")
    lines.append(f"- **Gauges:** {metric_types.get('gauge', 0)}")
    lines.append(f"- **Counters:** {metric_types.get('counter', 0)}")
    lines.append(f"- **Histograms:** {metric_types.get('histogram', 0)}")
    lines.append(f"- **Info metrics:** {metric_types.get('info', 0)}")
    lines.append("")

    by_category: dict[str, dict[str, list[MetricDefinition]]] = {"Collector": {}, "Internal": {}}
    for metric in metrics:
        by_category.setdefault(metric.category, {})
        by_category[metric.category].setdefault(metric.owner, []).append(metric)

    def render_section(title: str, owner_map: dict[str, list[MetricDefinition]]) -> None:
        if not owner_map:
            return
        lines.append(f"## {title}")
        lines.append("")
        for owner in sorted(owner_map.keys()):
            lines.append(f"### {owner}")
            lines.append("")
            lines.append("| Metric | Type | Labels | Description | Notes |")
            lines.append("|--------|------|--------|-------------|-------|")
            for metric in sorted(owner_map[owner], key=lambda m: m.name):
                labels = (
                    ", ".join(f"`{label}`" for label in metric.labels) if metric.labels else "—"
                )
                description = metric.description.replace("|", "\\|") if metric.description else ""
                notes = metric.notes or ""
                lines.append(
                    f"| `{metric.name}` | {metric.metric_type} | {labels} | {description} | {notes} |"
                )
            lines.append("")

    render_section("Collector Metrics", by_category.get("Collector", {}))
    render_section("Internal & Platform Metrics", by_category.get("Internal", {}))

    lines.append("## Metric Types")
    lines.append("")
    lines.append("- **Gauge**: Current value that can go up or down")
    lines.append("- **Counter**: Cumulative value that only increases")
    lines.append("- **Histogram**: Distribution of observations across buckets")
    lines.append("- **Info**: Metadata metric with labels and value 1")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    repo_root = find_repo_root(Path(__file__).resolve())
    src_path = repo_root / "src"
    constants_dir = repo_root / "src" / "meraki_dashboard_exporter" / "core" / "constants"
    metrics_file = repo_root / "src" / "meraki_dashboard_exporter" / "core" / "metrics.py"

    if not src_path.exists():
        print("Could not find src/ directory")
        return

    metric_name_map = parse_metric_constants(constants_dir)
    label_map = parse_label_constants(metrics_file)

    metrics = scan_for_metrics(src_path, repo_root, metric_name_map, label_map)
    print(f"Found {len(metrics)} metric definitions")

    markdown = generate_markdown(metrics)

    output_file = repo_root / "docs" / "metrics" / "metrics.md"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(markdown + "\n", encoding="utf-8")
    print(f"Documentation written to {output_file}")


if __name__ == "__main__":
    main()
