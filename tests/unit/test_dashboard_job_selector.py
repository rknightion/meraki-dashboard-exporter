"""The shipped Prometheus dashboards select the operator's scrape job."""

import json
import re
from pathlib import Path

import pytest

DASHBOARDS = Path(__file__).resolve().parents[2] / "grafana" / "dashboards"
PROMETHEUS_DASHBOARDS = (
    "meraki-clients.json",
    "meraki-devices.json",
    "meraki-network-health.json",
    "meraki-organization.json",
    "self-observability.json",
)


def nodes(value):
    """Walk nested dashboard objects."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def load(name):
    """Read a shipped dashboard."""
    return json.loads((DASHBOARDS / name).read_text())


@pytest.mark.parametrize("name", PROMETHEUS_DASHBOARDS)
def test_job_variable_and_prometheus_selectors(name):
    """A selectable job precedes variables that depend on it."""
    dashboard = load(name)
    variables = dashboard["spec"]["variables"]
    job = next(v["spec"] for v in variables if v["spec"]["name"] == "job")
    assert job["current"] == {"text": "meraki_dashboard", "value": "meraki_dashboard"}
    assert job["multi"] is True and job["includeAll"] is False
    assert (
        job["definition"]
        == job["query"]["spec"]["query"]
        == ("label_values(meraki_exporter_build_info, job)")
    )
    if any(v["spec"]["name"] == "organization" for v in variables):
        assert variables.index(
            next(v for v in variables if v["spec"]["name"] == "job")
        ) < variables.index(next(v for v in variables if v["spec"]["name"] == "organization"))


@pytest.mark.parametrize("path", sorted(DASHBOARDS.glob("*.json")))
def test_prometheus_expressions_select_job(path):
    """Every metric selector uses the selected job in both query copies."""
    dashboard = load(path.name)
    expressions = []
    for node in nodes(dashboard):
        if node.get("kind") == "prometheus":
            spec = node["spec"]
            expressions.append(spec.get("expr", spec.get("query", "")))
        if node.get("kind") == "QueryVariable":
            expressions.append(node["spec"]["definition"])
    for expression in expressions:
        if expression == "label_values(meraki_exporter_build_info, job)":
            continue
        assert not re.search(r'\bjob\s*=\s*"', expression), expression
        selectors = re.findall(r"\bmeraki_\w+\s*(\{[^{}]*\})?", expression)
        assert selectors, expression
        for selector in selectors:
            assert 'job=~"$job"' in selector, expression


def test_self_observability_datasource_targets():
    """Trace and log queries use configurable datasource UIDs."""
    dashboard = load("self-observability.json")
    variables = {v["spec"]["name"]: v for v in dashboard["spec"]["variables"]}
    for kind, uid in (("tempo", "grafanacloud-traces"), ("loki", "grafanacloud-logs")):
        variable = variables[f"{kind}_datasource"]
        assert variable["kind"] == "DatasourceVariable"
        assert variable["spec"]["pluginId"] == kind
        assert variable["spec"]["current"] == {"text": uid, "value": uid}
    targets = [node["spec"] for node in nodes(dashboard) if node.get("kind") == "PanelQuery"]
    for kind, count in (("tempo", 2), ("loki", 3)):
        matching = [target for target in targets if target["query"]["kind"] == kind]
        assert len(matching) == count
        assert all(
            target["datasource"] == {"type": kind, "uid": f"${{{kind}_datasource}}"}
            for target in matching
        )
