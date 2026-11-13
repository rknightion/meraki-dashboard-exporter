"""Contracts for device dashboard Prometheus queries."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[2] / "grafana/dashboards/meraki-devices.json"
NETWORK_MATCHER = 'network_id=~"$network"'
NETWORK_QUERIES = [
    ("panel-1", "A"),
    ("panel-2", "A"),
    ("panel-3", "A"),
    ("panel-4", "A"),
    ("panel-5", "A"),
    ("panel-6", "A"),
    ("panel-7", "A"),
    ("panel-8", "A"),
    ("panel-9", "A"),
    ("panel-27", "B"),
    *(("panel-29", ref) for ref in "ABCD"),
    *(("panel-30", ref) for ref in "AB"),
    *(("panel-31", ref) for ref in "ABC"),
    ("panel-32", "A"),
    ("panel-44", "A"),
    *(("panel-46", ref) for ref in "ABC"),
]


@pytest.fixture
def queries() -> dict[tuple[str, str], str]:
    """Read the Prometheus expressions by panel and reference."""
    dashboard = json.loads(DASHBOARD.read_text())
    return {
        (panel, query["spec"]["refId"]): query["spec"]["query"]["spec"]["expr"]
        for panel, element in dashboard["spec"]["elements"].items()
        for query in element["spec"]["data"]["spec"]["queries"]
        if query["spec"]["query"]["kind"] == "prometheus"
    }


def test_rate_functions_only_apply_to_counter_series(queries: dict[tuple[str, str], str]) -> None:
    """Window functions must not treat a snapshot gauge as a counter."""
    pattern = re.compile(r"\b(?:rate|irate|increase)\s*\(\s*([a-zA-Z_:][a-zA-Z0-9_:]*)")
    for expr in queries.values():
        # Reject unrecognized rate arguments rather than silently skipping them.
        assert len(pattern.findall(expr)) == len(
            re.findall(r"\b(?:rate|irate|increase)\s*\(", expr)
        )
    invalid = [
        (key, metric)
        for key, expr in queries.items()
        for metric in pattern.findall(expr)
        if not metric.endswith(("_total", "_bucket", "_sum"))
    ]
    assert invalid == []


def test_packet_panels_use_windowed_gauges(queries: dict[tuple[str, str], str]) -> None:
    """Packet loss divides the window counts; error panels read packet rates."""
    selector = 'job="meraki_dashboard", org_id=~"$organization", network_id=~"$network"'
    assert queries[("panel-15", "A")] == (
        f"sum(meraki_mr_packets_lost_count{{{selector}}}) / "
        f"(sum(meraki_mr_packets_count{{{selector}}}) > 0)"
    )
    assert (
        queries[("panel-23", "A")]
        == f"sum by (serial) (meraki_ms_port_packets_rate_crcerrors{{{selector}}})"
    )
    assert (
        queries[("panel-23", "B")]
        == f"sum by (serial) (meraki_ms_port_packets_rate_collisions{{{selector}}})"
    )


@pytest.mark.parametrize(("panel", "ref"), NETWORK_QUERIES)
def test_network_queries_filter_every_selector(
    queries: dict[tuple[str, str], str], panel: str, ref: str
) -> None:
    """Each targeted selector follows the Network picker."""
    selectors = re.findall(r"\{([^{}]*)\}", queries[(panel, ref)])
    assert selectors
    assert all(NETWORK_MATCHER in selector for selector in selectors)


@pytest.mark.parametrize(
    ("panel", "ref"), [("panel-18", "A"), ("panel-18", "B"), ("panel-26", "A")]
)
def test_org_only_queries_do_not_filter_network(
    queries: dict[tuple[str, str], str], panel: str, ref: str
) -> None:
    """Organization-only metrics cannot match a network label."""
    assert "network_id" not in queries[(panel, ref)]
