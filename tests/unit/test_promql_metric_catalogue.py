"""Keep shipped PromQL names in sync with the generated metric catalogue."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_metrics_docs as metrics_docs  # noqa: E402

DASHBOARDS = ROOT / "grafana/dashboards"
ALERTS = ROOT / "grafana/alerts"
EXAMPLES = ROOT / "examples/prometheus-rules.yaml"
CHART = ROOT / "charts/meraki-dashboard-exporter/templates/prometheusrule.yaml"
SOURCES = [
    *(
        DASHBOARDS / f"{name}.json"
        for name in (
            "meraki-devices",
            "meraki-organization",
            "meraki-clients",
            "meraki-network-health",
            "self-observability",
        )
    ),
    ALERTS / "alerting-rules.yaml",
    ALERTS / "recording-rules.yaml",
    EXAMPLES,
    CHART,
]
# Include newly shipped files in the gate as well as the fixed baseline floors.
ALL_SOURCES = sorted(set(SOURCES) | set(DASHBOARDS.glob("*.json")) | set(ALERTS.glob("*.yaml")))
QUOTED = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`""")
METRIC = re.compile(r"\bmeraki[A-Za-z0-9_:]*")


def _emitted_names() -> set[str]:
    constants = ROOT / "src/meraki_dashboard_exporter/core/constants"
    metrics_file = ROOT / "src/meraki_dashboard_exporter/core/metrics.py"
    definitions = metrics_docs.scan_for_metrics(
        ROOT / "src",
        ROOT,
        metrics_docs.parse_metric_constants(constants),
        metrics_docs.parse_label_constants(metrics_file),
    )
    names = set()
    for metric in definitions:
        if metric.metric_type == "histogram":
            names.update(metric.name + suffix for suffix in ("_bucket", "_sum", "_count"))
        elif metric.metric_type == "info":
            names.add(metric.name + "_info")
        elif metric.metric_type in {"gauge", "counter"}:
            names.add(metric.name)
    return names


def _chart_yaml() -> str:
    text = CHART.read_text(encoding="utf-8")
    text = re.sub(r'{{\s*"({{.*?}})"\s*}}', r"\1", text)
    text = re.sub(r"(?m)^\s*{{-?\s*(?:if|else|end|with|toYaml)\b[^\n]*}}\s*$", "", text)
    return re.sub(r"{{-?\s*(?:include\b|\.)[^\n]*?}}", "placeholder", text)


def _rules(path: Path) -> list[dict]:
    data = yaml.safe_load(_chart_yaml() if path == CHART else path.read_text(encoding="utf-8"))
    groups = data["groups"] if path.parent == ALERTS else data["spec"]["groups"]
    return [rule for group in groups for rule in group["rules"]]


def _expressions(path: Path) -> list[tuple[str, str]]:
    if path.parent != DASHBOARDS:
        return [
            (rule.get("alert", rule.get("record", "unnamed rule")), str(rule["expr"]))
            for rule in _rules(path)
            if "expr" in rule
        ]
    spec = json.loads(path.read_text(encoding="utf-8"))["spec"]
    found = []
    for key, element in spec["elements"].items():
        panel = element["spec"]
        for query in panel.get("data", {}).get("spec", {}).get("queries", []):
            query_spec = query["spec"]
            target = query_spec["query"]
            if target["kind"] == "prometheus":
                found.append((
                    f"panel {panel.get('title', key)} query {query_spec.get('refId', '?')}",
                    target["spec"]["expr"],
                ))
    for variable in spec["variables"]:
        if variable["kind"] == "QueryVariable":
            variable_spec = variable["spec"]
            target = variable_spec["query"]
            if target["kind"] == "prometheus":
                found.append((f"variable {variable_spec['name']}", target["spec"]["query"]))
    return found


def _unknown_names(expression: str, known: set[str]) -> set[str]:
    return set(METRIC.findall(QUOTED.sub(" ", expression))) - known


@pytest.fixture(scope="module")
def catalogue() -> set[str]:
    """Build emitted and recorded names once for all sources."""
    recorded = {
        rule["record"]
        for path in ALERTS.glob("*.yaml")
        for rule in _rules(path)
        if "record" in rule
    }
    return _emitted_names() | recorded


@pytest.mark.parametrize("path", ALL_SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_shipped_promql_names(path: Path, catalogue: set[str]) -> None:
    """Report unknown names with their source and location."""
    failures = [
        f"{path.relative_to(ROOT)}: {location}: {name}"
        for location, expr in _expressions(path)
        for name in sorted(_unknown_names(expr, catalogue))
    ]
    assert not failures, "\n" + "\n".join(failures)


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_source_has_expressions(path: Path) -> None:
    """Guard each baseline source against an empty extraction."""
    assert _expressions(path), f"No PromQL expressions found in {path.relative_to(ROOT)}"


def test_name_check(catalogue: set[str]) -> None:
    """Distinguish emitted and recorded names from strings and typos."""
    assert _unknown_names('meraki_device_upp{job="meraki_dashboard"}', catalogue) == {
        "meraki_device_upp"
    }
    assert not _unknown_names(
        "meraki_exporter_task_queue_wait_seconds_bucket + meraki_org_info + "
        "meraki:device_up:ratio + 'meraki_fake' + `meraki_fake`",
        catalogue | {"meraki:device_up:ratio"},
    )
