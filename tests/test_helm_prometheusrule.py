"""Helm alert rules match each scrape target and support configurable jobs."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CHART = REPO_ROOT / "charts" / "meraki-dashboard-exporter"


def _expressions(document: dict, groups_key: str) -> dict[str, str]:
    return {
        rule["alert"]: rule["expr"]
        for group in document[groups_key]
        for rule in group["rules"]
        if "alert" in rule
    }


def _render(*args: str) -> dict[str, str]:
    result = subprocess.run(
        [
            "helm",
            "template",
            "org-a",
            str(CHART),
            "--set",
            "meraki.apiKey=dummy",
            "--set",
            "prometheusRule.enabled=true",
            "--show-only",
            "templates/prometheusrule.yaml",
            *args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return _expressions(yaml.safe_load(result.stdout)["spec"], "groups")


def _rule_index(groups: list[dict]) -> dict[str, tuple[str, str, str, str]]:
    indexed = {}
    for group in groups:
        for rule in group["rules"]:
            name = rule["alert"]
            assert name not in indexed, f"duplicate alert: {name}"
            expr = re.sub(r'\bjob\s*(?:=~|!~|!=|=)\s*"(?:\\.|[^"\\])*"\s*,?\s*', "", rule["expr"])
            expr = re.sub(r",\s*}", "}", expr).replace("{}", "")
            indexed[name] = (
                group["name"],
                rule["for"],
                rule["labels"]["severity"],
                " ".join(expr.split()),
            )
    return indexed


@pytest.mark.parametrize(
    "path,key",
    [("examples/prometheus-rules.yaml", "spec"), ("grafana/alerts/alerting-rules.yaml", None)],
)
def test_alert_rule_parity(path: str, key: str | None) -> None:
    """Both static sets match the union of chart variants, apart from job selectors."""
    chart = {}
    for enabled in ("false", "true"):
        result = subprocess.run(
            [
                "helm",
                "template",
                "org-a",
                str(CHART),
                "--set",
                "meraki.apiKey=dummy",
                "--set",
                "prometheusRule.enabled=true",
                "--set",
                f"prometheusRule.webhooksEnabled={enabled}",
                "--show-only",
                "templates/prometheusrule.yaml",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        rendered = _rule_index(yaml.safe_load(result.stdout)["spec"]["groups"])
        for name in chart.keys() & rendered.keys():
            assert chart[name] == rendered[name]
        chart.update(rendered)
    document = yaml.safe_load((REPO_ROOT / path).read_text())
    mirror = _rule_index((document[key] if key else document)["groups"])
    assert mirror.keys() == chart.keys()
    assert mirror == chart


def test_liveness_defaults_to_release_service_name() -> None:
    """The default matches this release's ServiceMonitor job."""
    assert _render()["MerakiExporterDown"] == 'up{job=~"org-a-meraki-dashboard-exporter"} == 0'


def test_liveness_accepts_a_job_regex() -> None:
    """Operators can match more than one job."""
    expressions = _render("--set-string", "prometheusRule.job=org-a|org-b")
    assert expressions["MerakiExporterDown"] == 'up{job=~"org-a|org-b"} == 0'


@pytest.mark.parametrize("job", [r"meraki\.example", 'meraki"example'])
def test_liveness_quotes_job_regex(job: str, tmp_path: Path) -> None:
    """PromQL string escapes preserve the configured regular expression."""
    value_file = tmp_path / "job"
    value_file.write_text(job, encoding="utf-8")
    expressions = _render("--set-file", f"prometheusRule.job={value_file}")
    assert expressions["MerakiExporterDown"] == f"up{{job=~{json.dumps(job)}}} == 0"


@pytest.mark.parametrize(
    ("alert", "matching"),
    [
        ("MerakiExporterCollectorStale", "on(job, instance, collector)"),
        ("MerakiExporterSchedulerGroupStale", "on(job, instance, group)"),
    ],
)
def test_staleness_joins_match_target_in_chart_and_mirror(alert: str, matching: str) -> None:
    """Both copies join each target and the collector or group."""
    mirror = yaml.safe_load((REPO_ROOT / "grafana/alerts/alerting-rules.yaml").read_text())
    assert matching in _render()[alert]
    assert matching in _expressions(mirror, "groups")[alert]


@pytest.mark.parametrize(
    ("webhooks", "alert", "expected"),
    [
        (
            "false",
            "MerakiDeviceDown",
            'meraki_device_up == 0 and on (job, instance, org_id, serial) meraki_device_status_info{status="offline"}',
        ),
        (
            "true",
            "MerakiDeviceDownFastPath",
            'meraki_device_up == 0 unless on (job, instance, org_id, serial) meraki_device_status_info{status=~"alerting|dormant"}',
        ),
    ],
)
def test_device_down_expressions(webhooks: str, alert: str, expected: str) -> None:
    """Rendered paths and static rules select the same device states."""
    chart = _render("--set", f"prometheusRule.webhooksEnabled={webhooks}")[alert]
    mirror = _expressions(
        yaml.safe_load((REPO_ROOT / "grafana/alerts/alerting-rules.yaml").read_text()), "groups"
    )[alert]
    example = _expressions(
        yaml.safe_load((REPO_ROOT / "examples/prometheus-rules.yaml").read_text())["spec"], "groups"
    )[alert]
    assert mirror.count('job="meraki_dashboard"') == 2
    mirror = re.sub(r'job="meraki_dashboard",?', "", mirror).replace("{}", "")
    for expression in (chart, mirror, example):
        assert " ".join(expression.split()) == expected


def test_mirror_liveness_uses_job_regex() -> None:
    """The mirror uses the same matcher type as the chart."""
    mirror = yaml.safe_load((REPO_ROOT / "grafana/alerts/alerting-rules.yaml").read_text())
    assert (
        _expressions(mirror, "groups")["MerakiExporterDown"] == 'up{job=~"meraki_dashboard"} == 0'
    )
