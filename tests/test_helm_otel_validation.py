"""Helm render contracts for independent OpenTelemetry channels (MDE-0061)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CHART = REPO_ROOT / "charts" / "meraki-dashboard-exporter"
OTLP_PORT = 4317


def _helm_template(*args: str) -> subprocess.CompletedProcess[str]:
    """Render the chart with an API key and any additional Helm arguments."""
    command = [
        "helm",
        "template",
        "test-release",
        str(CHART),
        "--set",
        "meraki.apiKey=dummy",
        *args,
    ]
    return subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)


@pytest.mark.parametrize(
    ("enabled_setting", "error"),
    [
        (
            "config.otelEnabled=true",
            "config.otelEndpoint must be set when config.otelEnabled is true.",
        ),
        (
            "config.otelLogsEnabled=true",
            "config.otelLogsEndpoint or config.otelEndpoint must be set when "
            "config.otelLogsEnabled is true.",
        ),
        (
            "config.otelMetricsEnabled=true",
            "config.otelMetricsEndpoint or config.otelEndpoint must be set when "
            "config.otelMetricsEnabled is true.",
        ),
    ],
)
def test_helm_render_rejects_enabled_otlp_channel_without_resolved_endpoint(
    enabled_setting: str, error: str
) -> None:
    """Every independently enabled OTLP channel requires its own or shared endpoint."""
    result = _helm_template("--set", enabled_setting)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert error in output


@pytest.mark.parametrize(
    "enabled_setting",
    ["config.otelLogsEnabled=true", "config.otelMetricsEnabled=true"],
)
def test_helm_render_accepts_shared_endpoint_for_independent_channel(enabled_setting: str) -> None:
    """Logs and metrics may inherit the shared tracing endpoint."""
    result = _helm_template("--set", enabled_setting, "--set", "config.otelEndpoint=collector:4317")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("enabled_setting", "endpoint_setting"),
    [
        ("config.otelLogsEnabled=true", "config.otelLogsEndpoint=logs-collector:4317"),
        ("config.otelMetricsEnabled=true", "config.otelMetricsEndpoint=metrics-collector:4317"),
    ],
)
def test_helm_render_accepts_channel_specific_endpoint(
    enabled_setting: str, endpoint_setting: str
) -> None:
    """Logs and metrics may use endpoints distinct from the tracing endpoint."""
    result = _helm_template("--set", enabled_setting, "--set", endpoint_setting)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("enabled_setting", "endpoint_setting"),
    [
        ("config.otelEnabled=true", "config.otelEndpoint=traces-collector:4317"),
        ("config.otelLogsEnabled=true", "config.otelLogsEndpoint=logs-collector:4317"),
        ("config.otelMetricsEnabled=true", "config.otelMetricsEndpoint=metrics-collector:4317"),
    ],
)
def test_network_policy_allows_otlp_for_each_enabled_channel(
    enabled_setting: str, endpoint_setting: str
) -> None:
    """The chart-wide OTLP egress port is opened for each enabled channel."""
    result = _helm_template(
        "--set",
        "networkPolicy.enabled=true",
        "--set",
        enabled_setting,
        "--set",
        endpoint_setting,
    )

    assert result.returncode == 0, result.stderr
    documents = [document for document in yaml.safe_load_all(result.stdout) if document]
    network_policy = next(document for document in documents if document["kind"] == "NetworkPolicy")
    egress_ports = [
        port["port"] for rule in network_policy["spec"]["egress"] for port in rule.get("ports", [])
    ]

    assert OTLP_PORT in egress_ports
