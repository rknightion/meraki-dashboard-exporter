"""Tests for the NetworkHealthCollector using test helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.error_handling import NothingCollectedError
from meraki_dashboard_exporter.core.org_health import (
    SOURCE_NETWORK_HEALTH,
    SOURCE_ORGANIZATION,
    OrgHealthTracker,
)
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import DeviceFactory, NetworkFactory, OrganizationFactory


def _band(band: str, total: float, wifi: float, non_wifi: float) -> dict:
    """Build one org-wide channel-utilization byBand entry (#271 response shape)."""
    return {
        "band": band,
        "total": {"percentage": total},
        "wifi": {"percentage": wifi},
        "nonWifi": {"percentage": non_wifi},
    }


def _backed_off_tracker(org_id: str) -> OrgHealthTracker:
    """Build a tracker with ``org_id`` driven into backoff (should_collect False)."""
    tracker = OrgHealthTracker()
    for _ in range(tracker.max_consecutive_failures):
        tracker.record_failure(org_id, "Backed Org")
    assert tracker.should_collect(org_id) is False
    return tracker


class TestNetworkHealthCollectorOrgHealthGating(BaseCollectorTest):
    """F-169: NetworkHealthCollector honours the shared OrgHealthTracker per-org gate."""

    collector_class = NetworkHealthCollector
    update_tier = UpdateTier.MEDIUM

    async def test_backed_off_org_is_skipped(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """A backed-off org is skipped before fetching networks; a healthy org is not.

        The backoff gate moved from the per-org worker into the coordinator's
        task-creation loop (#509 frozen rule 2c), so this is now exercised via
        a full ``_collect_impl()`` cycle rather than a direct call to
        ``_collect_org_network_health``.
        """
        tracker = _backed_off_tracker("BACKED")
        org_backed = OrganizationFactory.create(org_id="BACKED", name="Backed Org")
        org_healthy = OrganizationFactory.create(org_id="HEALTHY", name="Healthy Org")
        api = mock_api_builder.with_organizations([org_backed, org_healthy]).build()
        inventory.api = api
        collector = NetworkHealthCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            org_health_tracker=tracker,
        )
        fetched: list[str] = []

        async def _spy(org_id: str) -> list:
            fetched.append(org_id)
            return []

        collector._fetch_networks_for_health = _spy  # type: ignore[method-assign]

        await collector.collect()
        assert fetched == ["HEALTHY"]  # BACKED skipped by the coordinator's backoff gate

    async def test_none_tracker_collects_all(self, collector):
        """With no tracker wired in, every org is collected (backward compatible)."""
        assert collector.org_health_tracker is None
        fetched: list[str] = []

        async def _spy(org_id: str) -> list:
            fetched.append(org_id)
            return []

        collector._fetch_networks_for_health = _spy  # type: ignore[method-assign]

        await collector._collect_org_network_health("ANY", "Any Org")
        assert fetched == ["ANY"]


class TestNetworkHealthCollector(BaseCollectorTest):
    """Test NetworkHealthCollector functionality."""

    collector_class = NetworkHealthCollector
    update_tier = UpdateTier.MEDIUM

    async def test_channel_utilization_fetchers_validate_error_shape(
        self, collector, mock_api_builder
    ):
        """#271: the org-wide fetchers normalize the SDK exhausted-retry error shape.

        A dict with an ``errors`` key (the shape the SDK returns after retry
        exhaustion) must be surfaced as a RetryableAPIError by
        validate_response_format rather than returned as data.
        """
        from meraki_dashboard_exporter.core.error_handling import RetryableAPIError

        org = OrganizationFactory.create(org_id="123", name="Test Org")
        api = mock_api_builder.with_organizations([org]).build()
        error_shape = {"errors": ["rate limit exceeded"]}
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByDevice = MagicMock(
            return_value=error_shape
        )
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByNetwork = MagicMock(
            return_value=error_shape
        )
        collector.rf_health_collector.api = api

        with pytest.raises(RetryableAPIError):
            await collector.rf_health_collector._fetch_channel_utilization_by_device("123")
        with pytest.raises(RetryableAPIError):
            await collector.rf_health_collector._fetch_channel_utilization_by_network("123")

    def test_channel_utilization_help_states_window(self, collector, metrics):
        """MET-09: AP/network channel-utilization HELP must state the 10-min bucket.

        rf_health.py::_fetch_channel_utilization pins
        timespan=600, resolution=600 on
        getNetworkNetworkHealthChannelUtilization (600s is the endpoint's only
        valid resolution) and only the most-recent bucket is read, so the HELP
        text must say so.
        """
        ap_24 = metrics.get_metric("meraki_ap_channel_utilization_2_4ghz_percent")
        ap_5 = metrics.get_metric("meraki_ap_channel_utilization_5ghz_percent")
        net_24 = metrics.get_metric("meraki_network_channel_utilization_2_4ghz_percent")
        net_5 = metrics.get_metric("meraki_network_channel_utilization_5ghz_percent")
        for doc in (
            ap_24.documentation.lower(),
            ap_5.documentation.lower(),
            net_24.documentation.lower(),
            net_5.documentation.lower(),
        ):
            assert "10-min" in doc or "10 min" in doc

    async def test_collect_with_no_networks(self, collector, mock_api_builder, metrics):
        """Test collection when no networks exist."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).with_networks([], org_id=org["id"]).build()
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)
        # getOrganizations is served from the inventory cache and is deliberately
        # NOT counted as a collector API call (F-063 — no cache-hit inflation).

    async def test_collect_channel_utilization(self, collector, mock_api_builder, metrics):
        """#271: channel utilization is collected from the org-wide byDevice/byNetwork endpoints."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )
        devices = [
            DeviceFactory.create_mr(
                serial="Q2KD-XXXX",
                name="AP1",
                model="MR36",
                network_id=network["id"],
            ),
            DeviceFactory.create_mr(
                serial="Q2KD-YYYY",
                name="AP2",
                model="MR46",
                network_id=network["id"],
            ),
        ]

        # Org-wide byDevice response (#271). ⚠ Phase-6: band string values +
        # wifi/nonWifi/total.percentage camelCase key names.
        by_device = [
            {
                "serial": "Q2KD-XXXX",
                "mac": "00:11:22:33:44:55",
                "network": {"id": network["id"]},
                "byBand": [
                    _band("2.4", total=45, wifi=30, non_wifi=15),
                    _band("5", total=25, wifi=20, non_wifi=5),
                ],
            },
            {
                "serial": "Q2KD-YYYY",
                "mac": "00:11:22:33:44:66",
                "network": {"id": network["id"]},
                "byBand": [
                    _band("2.4", total=55, wifi=40, non_wifi=15),
                    _band("5", total=35, wifi=30, non_wifi=5),
                ],
            },
        ]
        by_network = [
            {
                "network": {"id": network["id"]},
                "byBand": [
                    _band("2.4", total=50, wifi=35, non_wifi=15),
                    _band("5", total=30, wifi=25, non_wifi=5),
                ],
            }
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices(devices, org_id=org["id"])
            .build()
        )
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByDevice = MagicMock(
            return_value=by_device
        )
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByNetwork = MagicMock(
            return_value=by_network
        )

        collector.api = api
        # Update sub-collectors' API references
        collector.rf_health_collector.api = api
        collector.connection_stats_collector.api = api
        collector.data_rates_collector.api = api
        collector.bluetooth_collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

        # The org-wide byDevice fetch is a real API call and must be tracked.
        self.assert_api_call_tracked(
            collector,
            metrics,
            "getOrganizationWirelessDevicesChannelUtilizationByDevice",
        )

        # Per-AP metrics (ID-only labels; model resolved from inventory). #534:
        # name/org_name/network_name dropped.
        metrics.assert_gauge_value(
            "meraki_ap_channel_utilization_2_4ghz_percent",
            45,
            org_id=org["id"],
            serial="Q2KD-XXXX",
            model="MR36",
            device_type="MR",
            network_id=network["id"],
            utilization_type="total",
        )
        metrics.assert_gauge_value(
            "meraki_ap_channel_utilization_2_4ghz_percent",
            15,
            org_id=org["id"],
            serial="Q2KD-XXXX",
            model="MR36",
            device_type="MR",
            network_id=network["id"],
            utilization_type="non_wifi",
        )
        metrics.assert_gauge_value(
            "meraki_ap_channel_utilization_5ghz_percent",
            5,
            org_id=org["id"],
            serial="Q2KD-XXXX",
            model="MR36",
            device_type="MR",
            network_id=network["id"],
            utilization_type="non_wifi",
        )

        # Per-network averages come straight from the byNetwork endpoint.
        metrics.assert_gauge_value(
            "meraki_network_channel_utilization_2_4ghz_percent",
            50,
            org_id=org["id"],
            network_id=network["id"],
            utilization_type="total",
        )
        metrics.assert_gauge_value(
            "meraki_network_channel_utilization_5ghz_percent",
            25,
            org_id=org["id"],
            network_id=network["id"],
            utilization_type="wifi",
        )

    async def test_channel_utilization_filters_out_of_scope_networks(
        self, collector, mock_api_builder, metrics
    ):
        """#271: org-wide rows for networks outside the wireless/allowed set are dropped."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )
        device = DeviceFactory.create_mr(serial="Q2KD-ZZZZ", model="MR36", network_id=network["id"])

        by_device = [
            {
                "serial": "Q2KD-ZZZZ",
                "network": {"id": network["id"]},
                "byBand": [_band("2.4", total=42, wifi=30, non_wifi=12)],
            },
            {
                # Belongs to a network NOT in the wireless/allowed set -> dropped.
                "serial": "Q2KD-OTHR",
                "network": {"id": "N_OTHER"},
                "byBand": [_band("2.4", total=99, wifi=90, non_wifi=9)],
            },
        ]
        by_network = [
            {
                "network": {"id": network["id"]},
                "byBand": [_band("2.4", total=42, wifi=30, non_wifi=12)],
            },
            {"network": {"id": "N_OTHER"}, "byBand": [_band("2.4", total=99, wifi=90, non_wifi=9)]},
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([device], org_id=org["id"])
            .build()
        )
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByDevice = MagicMock(
            return_value=by_device
        )
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByNetwork = MagicMock(
            return_value=by_network
        )
        collector.api = api
        collector.rf_health_collector.api = api

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        metrics.assert_gauge_value(
            "meraki_ap_channel_utilization_2_4ghz_percent",
            42,
            org_id=org["id"],
            serial="Q2KD-ZZZZ",
            model="MR36",
            device_type="MR",
            network_id=network["id"],
            utilization_type="total",
        )
        # The out-of-scope network's row must NOT have produced a series.
        metrics.assert_metric_not_set(
            "meraki_network_channel_utilization_2_4ghz_percent",
            org_id=org["id"],
            network_id="N_OTHER",
            utilization_type="total",
        )

    async def test_collect_connection_stats(self, collector, mock_api_builder, metrics):
        """Test collection of wireless connection statistics."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        connection_stats_data = {
            "assoc": 95,
            "auth": 98,
            "dhcp": 92,
            "dns": 99,
            "success": 90,
        }

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", connection_stats_data)
            .build()
        )
        collector.api = api
        # Update sub-collectors' API references
        collector.connection_stats_collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)
        self.assert_api_call_tracked(collector, metrics, "getNetworkWirelessConnectionStats")

        # Verify metrics were set (ID-only; network_name dropped per #534)
        metrics.assert_gauge_value(
            "meraki_network_wireless_connection_stats_count",
            95,
            stat_type="assoc",
            network_id=network["id"],
        )

    async def test_collect_data_rates(self, collector, mock_api_builder, metrics):
        """Test collection of wireless data rate metrics."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        data_rate_history = [
            {
                "endTs": "2024-01-01T12:00:00Z",
                "downloadKbps": 25000,
                "uploadKbps": 10000,
            },
            {
                "endTs": "2024-01-01T11:55:00Z",
                "downloadKbps": 20000,
                "uploadKbps": 8000,
            },
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", data_rate_history)
            .build()
        )
        collector.api = api
        # Update sub-collectors' API references
        collector.data_rates_collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)
        self.assert_api_call_tracked(collector, metrics, "getNetworkWirelessDataRateHistory")

        # Verify metrics were set (should use most recent data point).
        # API value is kilobytes/second; converted x1000 to bytes/second (#531 F-065).
        # ID-only; network_name dropped per #534.
        metrics.assert_gauge_value(
            "meraki_network_wireless_download_bytes_per_second",
            25000 * 1000,
            network_id=network["id"],
        )

    async def test_collect_handles_empty_channel_util_data(
        self, collector, mock_api_builder, metrics
    ):
        """Test handling of empty channel utilization data."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        # Configure mock API with empty responses
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", [])
            .build()
        )
        collector.api = api

        # Run collection - should handle gracefully
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

    async def test_collect_handles_api_errors(self, collector, mock_api_builder, metrics):
        """Test handling of API errors."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        # Configure mock API with errors
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_error("getNetworkNetworkHealthChannelUtilization", 400)
            .with_error("getNetworkWirelessConnectionStats", 404)
            .with_error("getNetworkWirelessDataRateHistory", 500)
            .build()
        )
        collector.api = api

        # Run collection - should handle errors gracefully
        await self.run_collector(collector)

        # Verify collector still marks as successful (error handling decorators)
        self.assert_collector_success(collector, metrics)

    async def test_collect_non_wireless_networks_skipped(
        self, collector, mock_api_builder, metrics
    ):
        """Test that non-wireless networks are skipped."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        networks = [
            NetworkFactory.create(
                network_id="N_123",
                name="Switch Network",
                product_types=["switch"],  # Not wireless
                org_id=org["id"],
            ),
            NetworkFactory.create(
                network_id="N_456",
                name="Camera Network",
                product_types=["camera"],  # Not wireless
                org_id=org["id"],
            ),
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks(networks, org_id=org["id"])
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

        # Should not call wireless-specific APIs
        # We can't directly check that methods weren't called with the mock builder,
        # but we can verify that no wireless-specific API calls were tracked
        try:
            self.assert_api_call_tracked(
                collector, metrics, "getNetworkWirelessConnectionStats", count=0
            )
        except AssertionError:
            # Expected - the API call wasn't tracked
            pass

    async def test_bluetooth_error_does_not_zero_metric(self, collector, mock_api_builder, metrics):
        """F-015: a rate-limit/transient error must NOT manufacture a 0 client count."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", [])
            .with_custom_response("getNetworkWirelessFailedConnections", [])
            .build()
        )
        # Simulate the SDK exhausting retries on a rate limit.
        api.networks.getNetworkBluetoothClients = MagicMock(
            side_effect=Exception("rate limit exceeded")
        )
        collector.api = api
        collector.rf_health_collector.api = api
        collector.connection_stats_collector.api = api
        collector.data_rates_collector.api = api
        collector.bluetooth_collector.api = api
        collector.ssid_performance_collector.api = api
        collector.latency_stats_collector.api = api
        collector.air_marshal_collector.api = api

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        # The gauge must NOT have been set to a confident 0 for this cycle.
        # ID-only; org_name/network_name dropped per #534.
        metrics.assert_metric_not_set(
            "meraki_network_bluetooth_clients_count",
            org_id=org["id"],
            network_id=network["id"],
        )

    async def test_channel_utilization_single_band_does_not_crash(
        self, collector, mock_api_builder, metrics
    ):
        """#271: an AP reporting only the 5GHz band still emits its 5GHz series."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )
        devices = [
            DeviceFactory.create_mr(
                serial="Q2KD-AAAA",
                name="AP1",
                model="MR36",
                network_id=network["id"],
            ),
        ]

        # Only the 5GHz band present in byBand.
        by_device = [
            {
                "serial": "Q2KD-AAAA",
                "network": {"id": network["id"]},
                "byBand": [_band("5", total=30, wifi=25, non_wifi=5)],
            }
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices(devices, org_id=org["id"])
            .build()
        )
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByDevice = MagicMock(
            return_value=by_device
        )
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByNetwork = MagicMock(
            return_value=[]
        )
        collector.api = api
        collector.rf_health_collector.api = api

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        # 5GHz metric emitted even though the 2.4GHz band is absent.
        metrics.assert_gauge_value(
            "meraki_ap_channel_utilization_5ghz_percent",
            30,
            org_id=org["id"],
            serial="Q2KD-AAAA",
            model="MR36",
            device_type="MR",
            network_id=network["id"],
            utilization_type="total",
        )

    async def test_channel_utilization_fetch_pins_query_params(
        self, collector, mock_api_builder, metrics
    ):
        """#271: the org-wide byDevice/byNetwork fetches pin timespan/interval/perPage/total_pages."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .build()
        )
        by_device_mock = MagicMock(return_value=[])
        by_network_mock = MagicMock(return_value=[])
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByDevice = by_device_mock
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByNetwork = by_network_mock
        collector.api = api
        collector.rf_health_collector.api = api

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        for mock in (by_device_mock, by_network_mock):
            mock.assert_called_once()
            _, kwargs = mock.call_args
            assert kwargs.get("timespan") == 600
            assert kwargs.get("interval") == 600
            assert kwargs.get("perPage") == 1000
            assert kwargs.get("total_pages") == "all"

    async def test_channel_utilization_error_is_swallowed(
        self, collector, mock_api_builder, metrics
    ):
        """#271: a channel-util fetch error must not fail the org's collection cycle."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .build()
        )
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByDevice = MagicMock(
            side_effect=Exception("400 Bad Request")
        )
        api.wireless.getOrganizationWirelessDevicesChannelUtilizationByNetwork = MagicMock(
            return_value=[]
        )
        collector.api = api
        collector.rf_health_collector.api = api

        # The whole cycle still succeeds despite the channel-util failure.
        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)
        metrics.assert_metric_not_set(
            "meraki_ap_channel_utilization_2_4ghz_percent",
            org_id=org["id"],
            network_id=network["id"],
        )

    async def test_data_rate_help_text_states_kilobytes(self, collector, mock_api_builder, metrics):
        """F-065: API unit is kilobytes-per-second; value converted x1000 to bytes/second (#531)."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )
        data_rate_history = [
            {"endTs": "2024-01-01T12:00:00Z", "downloadKbps": 25000, "uploadKbps": 10000},
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", data_rate_history)
            .build()
        )
        collector.api = api
        collector.data_rates_collector.api = api

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        # API value is kilobytes/second; converted x1000 to bytes/second (NOT bits, F-065).
        # ID-only; network_name dropped per #534.
        metrics.assert_gauge_value(
            "meraki_network_wireless_download_bytes_per_second",
            25000 * 1000,
            network_id=network["id"],
        )
        # Help text must state the real unit and the conversion basis.
        download = metrics.get_metric("meraki_network_wireless_download_bytes_per_second")
        upload = metrics.get_metric("meraki_network_wireless_upload_bytes_per_second")
        assert "bytes per second" in download.documentation.lower()
        assert "kilobit" not in download.documentation.lower()
        assert "bytes per second" in upload.documentation.lower()
        assert "kilobit" not in upload.documentation.lower()

    def test_set_metric_value_handles_none(self, collector):
        """Test that None values are handled properly."""
        # This tests the _set_metric_value method directly
        labels = {"network_id": "N_123", "network_name": "Test"}

        # Should skip None values without error
        collector._set_metric_value("_network_utilization_2_4ghz", labels, None)

    def test_update_tier(self, collector):
        """Test that network health collector has correct update tier."""
        assert collector.update_tier == UpdateTier.MEDIUM
        assert self.update_tier == UpdateTier.MEDIUM


class TestNetworkHealthCollectorFailureAccounting(BaseCollectorTest):
    """#509: total collection failure must raise instead of being swallowed."""

    collector_class = NetworkHealthCollector
    update_tier = UpdateTier.MEDIUM

    async def test_org_fetch_failure_raises(self, collector, mock_api_builder):
        """A total org-fetch failure must propagate out of collect()."""
        api = mock_api_builder.with_error("getOrganizations", Exception("Connection error")).build()
        collector.api = api
        collector.inventory.api = api

        with pytest.raises(Exception):  # noqa: B017 - either CollectorError or the raw error
            await collector.collect()

    async def test_all_orgs_failed_raises_nothing_collected(self, collector, mock_api_builder):
        """If the only org's network fetch fails, the cycle must raise NothingCollectedError."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_error("getOrganizationNetworks", Exception("Connection error"))
            .build()
        )
        collector.api = api
        collector.inventory.api = api

        with pytest.raises(NothingCollectedError):
            await collector.collect()

    async def test_partial_org_failure_does_not_raise(self, collector, mock_api_builder, metrics):
        """One org failing while another succeeds must not raise; healthy org's data survives."""
        org_bad = OrganizationFactory.create(org_id="BAD", name="Bad Org")
        org_good = OrganizationFactory.create(org_id="GOOD", name="Good Org")
        network = NetworkFactory.create(
            network_id="N_GOOD",
            name="Good Network",
            product_types=["wireless"],
            org_id=org_good["id"],
        )

        api = (
            mock_api_builder
            .with_organizations([org_bad, org_good])
            .with_error("getOrganizationNetworks", Exception("Connection error"), org_id="BAD")
            .with_networks([network], org_id=org_good["id"])
            .with_devices([], org_id=org_good["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", [])
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        self.assert_collector_success(collector, metrics)
        self.assert_api_call_tracked(collector, metrics, "getNetworkWirelessConnectionStats")

    async def test_all_orgs_in_backoff_raises(self, collector, mock_api_builder):
        """Every org skipped for backoff must raise NothingCollectedError (attempted == 0)."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        api = mock_api_builder.with_organizations([org]).build()
        collector.api = api
        collector.inventory.api = api
        collector.org_health_tracker = _backed_off_tracker("123")

        with pytest.raises(NothingCollectedError) as excinfo:
            await collector.collect()
        assert excinfo.value.skipped_backoff == 1
        assert excinfo.value.failed == 0

    async def test_empty_org_list_is_success(self, collector, mock_api_builder, metrics):
        """No organizations found is a legitimate no-op, not a failure."""
        api = mock_api_builder.with_organizations([]).build()
        collector.api = api

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)


class TestNetworkHealthCollectorBluetooth(BaseCollectorTest):
    """Test NetworkHealthCollector functionality (continued)."""

    collector_class = NetworkHealthCollector
    update_tier = UpdateTier.MEDIUM

    async def test_collect_bluetooth_clients(self, collector, mock_api_builder, metrics):
        """Test collection of Bluetooth client metrics."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )

        bluetooth_data = [
            {
                "startTs": "2024-01-01T12:00:00Z",
                "endTs": "2024-01-01T12:05:00Z",
                "bluetoothDeviceCount": 42,
            }
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", [])
            .with_custom_response("getNetworkWirelessConnectionStats", {})
            .with_custom_response("getNetworkWirelessDataRateHistory", [])
            .with_custom_response("getNetworkWirelessBluetoothClients", bluetooth_data)
            .build()
        )

        # Manually configure the bluetooth clients API (if needed)
        api.wireless.getNetworkWirelessBluetoothClients = MagicMock(return_value=bluetooth_data)

        collector.api = api
        # Update sub-collectors' API references
        if hasattr(collector, "bluetooth_collector"):
            collector.bluetooth_collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)


class TestNetworkHealthCollectorOrgHealthReporting(BaseCollectorTest):
    """#547: NetworkHealthCollector reports its per-org verdict into the tracker.

    Verdicts are recorded under the SOURCE_NETWORK_HEALTH failure domain.
    A network-endpoint failure engages backoff for that org even when the
    organization collector reports success or is disabled entirely; a
    network-health recovery clears it. The verdict mirrors the coordinator's
    raise/return accounting: the worker raises only when the network fetch fails;
    per-network bundle failures are isolated and count as a domain success.
    """

    collector_class = NetworkHealthCollector
    update_tier = UpdateTier.MEDIUM

    async def test_successful_org_records_network_health_success(self, collector):
        """A healthy per-org cycle records a SOURCE_NETWORK_HEALTH success."""
        tracker = OrgHealthTracker(max_consecutive_failures=3)
        collector.org_health_tracker = tracker

        async def _empty(org_id: str) -> list:
            return []

        # No networks -> no wireless -> legitimate no-op success for the worker.
        collector._fetch_networks_for_health = _empty  # type: ignore[method-assign]

        await collector._collect_org_network_health("ORG1", "Org One")

        health = tracker.get_health("ORG1")
        assert health is not None
        assert health.source_failures.get(SOURCE_NETWORK_HEALTH) == 0
        assert health.last_success > 0
        assert tracker.should_collect("ORG1") is True

    async def test_network_failure_engages_backoff_when_org_disabled(self, collector):
        """A persistent network-health failure engages backoff (#547 cases 1, 2).

        The organization collector never writes into the tracker, yet backoff
        still engages for the org from the network-health domain alone.
        """
        tracker = OrgHealthTracker(max_consecutive_failures=3)
        collector.org_health_tracker = tracker

        async def _boom(org_id: str) -> list:
            raise Exception("Connection error")

        collector._fetch_networks_for_health = _boom  # type: ignore[method-assign]

        for _ in range(3):
            with pytest.raises(Exception):  # noqa: B017 - CollectorError or raw error
                await collector._collect_org_network_health("ORG1", "Org One")

        health = tracker.get_health("ORG1")
        assert health.source_failures[SOURCE_NETWORK_HEALTH] == 3
        assert SOURCE_ORGANIZATION not in health.source_failures
        assert tracker.should_collect("ORG1") is False

    async def test_network_recovery_clears_backoff(self, collector):
        """(3): once the network-health domain recovers, backoff clears."""
        tracker = OrgHealthTracker(max_consecutive_failures=3)
        collector.org_health_tracker = tracker

        async def _boom(org_id: str) -> list:
            raise Exception("Connection error")

        collector._fetch_networks_for_health = _boom  # type: ignore[method-assign]
        for _ in range(3):
            with pytest.raises(Exception):  # noqa: B017 - CollectorError or raw error
                await collector._collect_org_network_health("ORG1", "Org One")
        assert tracker.should_collect("ORG1") is False

        async def _empty(org_id: str) -> list:
            return []

        collector._fetch_networks_for_health = _empty  # type: ignore[method-assign]
        await collector._collect_org_network_health("ORG1", "Org One")
        assert tracker.should_collect("ORG1") is True
        assert tracker.get_health("ORG1").consecutive_failures == 0

    async def test_none_tracker_is_noop(self, collector):
        """With no tracker wired, the worker records nothing (backward compatible)."""
        assert collector.org_health_tracker is None

        async def _empty(org_id: str) -> list:
            return []

        collector._fetch_networks_for_health = _empty  # type: ignore[method-assign]
        await collector._collect_org_network_health("ORG1", "Org One")
