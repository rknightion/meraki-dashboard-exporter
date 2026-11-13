"""Network health success rate uses all reported connection outcomes."""

import json
import re
from pathlib import Path


def test_success_rate_counts_all_outcomes() -> None:
    """The denominator includes every outcome and excludes empty windows."""
    dashboard = json.loads(
        Path("grafana/dashboards/meraki-network-health.json").read_text(encoding="utf-8")
    )
    panels = dashboard["spec"]["elements"]
    panel = panels["panel-2"]["spec"]
    expr = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["expr"]
    selectors = re.findall(r"meraki_network_wireless_connection_stats_count\{([^}]*)\}", expr)
    assert len(selectors) == 2
    assert 'stat_type="success"' in selectors[0]
    assert "stat_type" not in selectors[1]
    assert "clamp_min" not in expr
    assert 'stat_type="assoc"' not in expr
    assert " / (sum(meraki_network_wireless_connection_stats_count{" in expr
    assert ") > 0)) * 100" in expr
    for labels in selectors:
        assert 'job="meraki_dashboard"' in labels
        assert 'org_id=~"$organization"' in labels
        assert 'network_id=~"$network"' in labels
    assert "success + assoc + auth + dhcp + dns" in panel["description"]
    for panel_id in ("panel-1", "panel-3"):
        assert "funnel" not in panels[panel_id]["spec"]["title"].lower()
