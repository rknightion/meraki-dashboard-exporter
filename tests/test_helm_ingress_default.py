"""Helm render contract: the default Ingress publishes only the webhook receiver."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CHART = REPO_ROOT / "charts" / "meraki-dashboard-exporter"
WEBHOOK_PATH = "/api/webhooks/meraki"


def _render_ingress(*args: str) -> dict:
    """Render only the Ingress with an API key, Ingress enabled and any extra arguments."""
    command = [
        "helm",
        "template",
        "test-release",
        str(CHART),
        "--set",
        "meraki.apiKey=dummy",
        "--set",
        "ingress.enabled=true",
        "--show-only",
        "templates/ingress.yaml",
        *args,
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    documents = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    assert len(documents) == 1
    return documents[0]


def _paths(ingress: dict) -> list[str]:
    return [path["path"] for rule in ingress["spec"]["rules"] for path in rule["http"]["paths"]]


def test_default_ingress_routes_only_the_webhook_path() -> None:
    """Enabling the Ingress with defaults must not publish the UI, /config or /metrics."""
    assert _paths(_render_ingress()) == [WEBHOOK_PATH]


def test_default_ingress_path_matches_the_app_route() -> None:
    """The chart default and the app's webhook route stay the same string."""
    app_source = (REPO_ROOT / "src" / "meraki_dashboard_exporter" / "app.py").read_text()
    assert f'@app.post("{WEBHOOK_PATH}")' in app_source
