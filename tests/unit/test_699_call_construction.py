"""Page-aware bulk request construction stays bounded (#699)."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from meraki_dashboard_exporter.collectors.organization import OrganizationCollector
from meraki_dashboard_exporter.core.error_handling import ErrorCategory
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest

_ROOT = Path(__file__).parents[2]


def _function_keywords(source_file: str, function_name: str) -> set[str]:
    tree = ast.parse((_ROOT / source_file).read_text())
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )
    return {
        keyword.arg
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg is not None
    }


def test_api_request_log_uses_documented_maximum_page_size() -> None:
    """The one-hour request-log bulk fetch avoids the SDK default of 50 rows/page."""
    assert "perPage" in _function_keywords(
        "src/meraki_dashboard_exporter/collectors/organization_collectors/api_usage.py",
        "_fetch_api_requests",
    )


def test_org_wide_switch_fetches_do_not_expand_every_serial_into_the_url() -> None:
    """Org-wide endpoints rely on org scope and pagination rather than serial filters."""
    for function_name in ("collect_port_statuses_by_switch", "collect_port_usage_by_switch"):
        tree = ast.parse(
            (_ROOT / "src/meraki_dashboard_exporter/collectors/devices/ms.py").read_text()
        )
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        )
        facade_calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "call"
        ]
        assert facade_calls
        assert all(
            "serials" not in {keyword.arg for keyword in call.keywords} for call in facade_calls
        )


def test_api_usage_group_cost_includes_expected_bulk_pages() -> None:
    """The scheduler accounts for overview plus the bounded one-hour page ceiling."""
    from meraki_dashboard_exporter.collectors.organization import OrganizationCollector
    from meraki_dashboard_exporter.core.scheduler import EndpointGroupName, OrgShape

    group = next(
        group
        for group in OrganizationCollector.endpoint_groups
        if group.name is EndpointGroupName.ORG_API_USAGE
    )
    shape = OrgShape(
        org_id="O1",
        network_count=0,
        wireless_network_count=0,
        switch_network_count=0,
        appliance_network_count=0,
        sensor_network_count=0,
        camera_network_count=0,
        cellular_network_count=0,
        device_count=0,
        ap_count=0,
        switch_count=0,
        appliance_count=0,
        physical_mx_count=0,
        camera_count=0,
        sensor_count=0,
        cellular_count=0,
    )
    assert group.cost_fn(shape) == 37


class TestApiUsageCompleteness(BaseCollectorTest):
    """The bulk enrichment must not silently report a complete group."""

    collector_class = OrganizationCollector

    async def test_request_log_uses_exact_documented_page_size(self, collector) -> None:
        """The emitted SDK call requests the endpoint maximum of 1,000 rows."""
        collector.api.organizations.getOrganizationApiRequests.return_value = []

        await collector.api_usage_collector._fetch_api_requests("org-1")

        call = collector.api.organizations.getOrganizationApiRequests.call_args
        assert call.kwargs["perPage"] == 1000
        assert call.kwargs["total_pages"] == "all"

    async def test_deadline_cut_enrichment_preserves_overview_success(self, collector) -> None:
        """A timed-out enrichment is observable without failing the fresh overview."""
        subcollector = collector.api_usage_collector
        subcollector._fetch_api_requests_overview = AsyncMock(  # type: ignore[method-assign]
            return_value={"responseCodeCounts": {"200": 1}}
        )
        subcollector._collect_requests_by_operation = AsyncMock(  # type: ignore[method-assign]
            side_effect=TimeoutError("bulk fetch deadline exceeded")
        )
        collector._mark_group_ran = MagicMock()  # type: ignore[method-assign]
        collector._track_error = MagicMock()  # type: ignore[method-assign]

        assert await subcollector.collect("org-1", "Org") is True

        collector._mark_group_ran.assert_called_once_with(EndpointGroupName.ORG_API_USAGE)
        collector._track_error.assert_called_once_with(ErrorCategory.TIMEOUT)
