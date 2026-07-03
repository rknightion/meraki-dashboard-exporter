"""Tests for the TopUsageCollector (#299)."""

from __future__ import annotations

import pytest

from meraki_dashboard_exporter.collectors.organization_collectors.top_usage import (
    TopUsageCollector,
)


class _MockParent:
    def __init__(self, api) -> None:
        self.api = api
        self.settings = None
        self._metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    def _should_run_group(self, group: object) -> bool:
        return True

    def _mark_group_ran(self, group: object) -> None:
        pass

    def _group_ttl_seconds(self, group: object) -> float | None:
        return None

    def _track_api_call(self, method_name: str) -> None:
        pass

    def _set_metric_value(
        self,
        metric_name: str,
        labels: dict[str, str],
        value: float | None,
        ttl_seconds: float | None = None,
    ) -> None:
        if value is not None:
            key = (metric_name, tuple(sorted(labels.items())))
            self._metrics[key] = value


class TestTopUsageCollector:
    """Test TopUsageCollector functionality."""

    @pytest.fixture
    def mock_api_builder(self):
        """Create a mock API builder."""
        from tests.helpers.mock_api import MockAPIBuilder

        return MockAPIBuilder()

    def _collector(self, mock_api_builder) -> TopUsageCollector:
        parent = _MockParent(mock_api_builder.build())
        return TopUsageCollector(parent=parent)  # type: ignore[arg-type]

    async def test_collect_top_usage_bytes_conversion(self, mock_api_builder):
        """kB-reported usage is converted to bytes (x1000) and labelled by id/name."""
        org_id = "org1"
        org_name = "Org One"

        api = (
            mock_api_builder
            .with_custom_response(
                "getOrganizationSummaryTopClientsByUsage",
                [
                    {"id": "client-a", "name": "10.0.0.1", "usage": {"total": 5}},
                    {"id": "client-b", "name": "10.0.0.2", "usage": {"total": 10}},
                ],
            )
            .with_custom_response(
                "getOrganizationSummaryTopSsidsByUsage",
                [{"name": "Corp-WiFi", "usage": {"total": 3}}],
            )
            .with_custom_response(
                "getOrganizationSummaryTopClientsManufacturersByUsage",
                [{"name": "Apple", "usage": {"total": 7}}],
            )
            .build()
        )
        collector = self._collector(mock_api_builder)
        collector.api = api

        result = await collector.collect(org_id, org_name)
        assert result is True

        m = collector.parent._metrics
        assert (
            m[
                (
                    "_org_top_client_usage_total_bytes",
                    (("client_id", "client-a"), ("org_id", org_id)),
                )
            ]
            == 5000
        )
        assert (
            m[
                (
                    "_org_top_client_usage_total_bytes",
                    (("client_id", "client-b"), ("org_id", org_id)),
                )
            ]
            == 10000
        )
        assert (
            m[("_org_top_ssid_usage_total_bytes", (("org_id", org_id), ("ssid", "Corp-WiFi")))]
            == 3000
        )
        assert (
            m[
                (
                    "_org_top_manufacturer_usage_total_bytes",
                    (("manufacturer", "Apple"), ("org_id", org_id)),
                )
            ]
            == 7000
        )

        # quantity=10 requested on every leaderboard endpoint.
        assert (
            api.organizations.getOrganizationSummaryTopClientsByUsage.call_args[1]["quantity"] == 10
        )
        assert (
            api.organizations.getOrganizationSummaryTopSsidsByUsage.call_args[1]["quantity"] == 10
        )
        assert (
            api.organizations.getOrganizationSummaryTopClientsManufacturersByUsage.call_args[1][
                "quantity"
            ]
            == 10
        )

    async def test_client_id_fallback_and_missing_id_skipped(self, mock_api_builder):
        """clientId is used when id is absent; an entry with neither is skipped."""
        org_id = "org2"

        api = (
            mock_api_builder
            .with_custom_response(
                "getOrganizationSummaryTopClientsByUsage",
                [
                    {"clientId": "client-c", "usage": {"total": 2}},
                    {"usage": {"total": 99}},  # no id/clientId -> skipped
                ],
            )
            .with_custom_response("getOrganizationSummaryTopSsidsByUsage", [])
            .with_custom_response("getOrganizationSummaryTopClientsManufacturersByUsage", [])
            .build()
        )
        collector = self._collector(mock_api_builder)
        collector.api = api

        await collector.collect(org_id, "Org Two")

        m = collector.parent._metrics
        assert (
            m[
                (
                    "_org_top_client_usage_total_bytes",
                    (("client_id", "client-c"), ("org_id", org_id)),
                )
            ]
            == 2000
        )
        # Only one client series should exist (the id-less one was skipped).
        client_keys = [k for k in m if k[0] == "_org_top_client_usage_total_bytes"]
        assert len(client_keys) == 1

    async def test_collect_handles_404(self, mock_api_builder):
        """A 404 on the leaderboard endpoints is a benign skip (returns True)."""
        api = mock_api_builder.with_error(
            "getOrganizationSummaryTopClientsByUsage", Exception("404 Not Found")
        ).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        result = await collector.collect("org3", "Org Three")
        assert result is True
        assert len(collector.parent._metrics) == 0

    async def test_missing_usage_yields_zero(self, mock_api_builder):
        """An entry with no usage container reports 0 rather than raising."""
        org_id = "org4"
        api = (
            mock_api_builder
            .with_custom_response(
                "getOrganizationSummaryTopClientsByUsage",
                [{"id": "client-d"}],  # no usage key
            )
            .with_custom_response("getOrganizationSummaryTopSsidsByUsage", [])
            .with_custom_response("getOrganizationSummaryTopClientsManufacturersByUsage", [])
            .build()
        )
        collector = self._collector(mock_api_builder)
        collector.api = api

        await collector.collect(org_id, "Org Four")
        m = collector.parent._metrics
        assert (
            m[
                (
                    "_org_top_client_usage_total_bytes",
                    (("client_id", "client-d"), ("org_id", org_id)),
                )
            ]
            == 0
        )
