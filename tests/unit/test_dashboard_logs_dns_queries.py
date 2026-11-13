"""Contracts for DNS and default JSON log dashboard queries."""

import json
from pathlib import Path

import pytest

DASHBOARDS = Path("grafana/dashboards")


def _panel(filename: str, panel: str) -> dict:
    data = json.loads((DASHBOARDS / filename).read_text(encoding="utf-8"))
    return data["spec"]["elements"][panel]["spec"]


def _query(panel: dict) -> str:
    queries = panel["data"]["spec"]["queries"]
    return next(q["spec"]["query"]["spec"]["expr"] for q in queries if q["spec"]["refId"] == "A")


def test_dns_latency_uses_positive_uncached_lookup_rate() -> None:
    """Low lookup rates are not clamped to one lookup per second."""
    expr = _query(_panel("meraki-clients.json", "panel-14"))
    assert "clamp_min" not in expr
    assert "> 0" in expr


@pytest.mark.parametrize("panel_id", ["panel-23", "panel-24"])
def test_logs_parse_json_and_filter_errors(panel_id: str) -> None:
    """Default JSON logs are parsed and malformed lines are filtered."""
    panel = _panel("self-observability.json", panel_id)
    expr = _query(panel)
    assert '| json | __error__=""' in expr
    assert "| logfmt" not in expr
    if panel_id == "panel-23":
        assert "logfmt-parsed" not in panel["description"]


def test_client_telemetry_has_no_stale_emission_warning() -> None:
    """Dashboard text does not claim the fixed wireless emission is pending."""
    text = (DASHBOARDS / "meraki-client-telemetry.json").read_text(encoding="utf-8")
    for stale in ("637", "No data", "LIVE-VERIFIED", "ASSUMED"):
        assert stale not in text
