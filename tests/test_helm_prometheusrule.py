"""Helm alert rules match each scrape target and support configurable jobs."""

from __future__ import annotations

import json
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


def test_mirror_liveness_uses_job_regex() -> None:
    """The mirror uses the same matcher type as the chart."""
    mirror = yaml.safe_load((REPO_ROOT / "grafana/alerts/alerting-rules.yaml").read_text())
    assert (
        _expressions(mirror, "groups")["MerakiExporterDown"] == 'up{job=~"meraki_dashboard"} == 0'
    )
