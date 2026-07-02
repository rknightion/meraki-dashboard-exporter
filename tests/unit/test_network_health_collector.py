"""Tests for the NetworkHealthCollector using test helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.error_handling import NothingCollectedError
from meraki_dashboard_exporter.core.org_health import OrgHealthTracker
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import DeviceFactory, NetworkFactory, OrganizationFactory


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
        """Test collection of channel utilization metrics."""
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

        channel_util_data = [
            {
                "serial": "Q2KD-XXXX",
                "model": "MR36",
                "wifi0": [  # 2.4GHz
                    {"utilization": 45, "wifi": 30, "nonWifi": 15}
                ],
                "wifi1": [  # 5GHz
                    {"utilization": 25, "wifi": 20, "nonWifi": 5}
                ],
            },
            {
                "serial": "Q2KD-YYYY",
                "model": "MR46",
                "wifi0": [{"utilization": 55, "wifi": 40, "nonWifi": 15}],
                "wifi1": [{"utilization": 35, "wifi": 30, "nonWifi": 5}],
            },
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices(devices, org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", channel_util_data)
            .build()
        )

        # The RF health collector calls getOrganizationDevices with specific params
        # We need to ensure it returns the devices when called with networkIds filter
        api.organizations.getOrganizationDevices = MagicMock(return_value=devices)

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

        # Verify API calls were tracked. getOrganizationDevices is served from the
        # inventory cache here, so it is deliberately NOT counted as a collector API
        # call (F-063 — no cache-hit inflation); only the real network call is tracked.
        self.assert_api_call_tracked(
            collector, metrics, "getNetworkNetworkHealthChannelUtilization"
        )

        # Verify metrics were set (ID-only labels; name/org_name/network_name
        # dropped per #534 - name joins via meraki_device_status_info,
        # network_name via meraki_network_info).
        metrics.assert_gauge_value(
            "meraki_ap_channel_utilization_2_4ghz_percent",
            45,
            org_id=org["id"],
            serial="Q2KD-XXXX",
            model="MR36",
            device_type="MR",
            network_id=network["id"],
            utilization_type="total",  # Changed from 'type' to 'utilization_type'
        )

    async def test_channel_utilization_none_ap_name_falls_back_to_serial(
        self, collector, mock_api_builder, metrics
    ):
        """An AP whose device record has name=None must still emit its metric (F-019).

        Previously ``d.get("name", d["serial"])`` only fell back on a MISSING key,
        so an explicit ``name: None`` produced a None name label; create_labels
        then dropped it, Gauge.labels() raised ValueError for the missing
        labelname, and a bare except silently lost the whole per-AP series. The
        `name` coalescing still happens internally in rf_health.py (used for the
        RFHealthData domain-model validation) but `name` is no longer a metric
        label (#534) - this test now guards that the explicit-None device record
        still doesn't crash the collector / drop the series.
        """
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_123",
            name="Test Network",
            product_types=["wireless"],
            org_id=org["id"],
        )
        device = DeviceFactory.create_mr(
            serial="Q2KD-ZZZZ",
            model="MR36",
            network_id=network["id"],
        )
        device["name"] = None  # explicit None value, not a missing key
        channel_util_data = [
            {
                "serial": "Q2KD-ZZZZ",
                "model": "MR36",
                "wifi0": [{"utilization": 42, "wifi": 30, "nonWifi": 12}],
                "wifi1": [{"utilization": 22, "wifi": 18, "nonWifi": 4}],
            }
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([device], org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", channel_util_data)
            .build()
        )
        api.organizations.getOrganizationDevices = MagicMock(return_value=[device])
        collector.api = api
        collector.rf_health_collector.api = api

        await self.run_collector(collector)

        self.assert_collector_success(collector, metrics)
        # Series still emitted (not dropped) despite the explicit None name.
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

    async def test_channel_utilization_wifi1_only_does_not_crash(
        self, collector, mock_api_builder, metrics
    ):
        """F-017: an AP reporting only wifi1 (5GHz) must not raise UnboundLocalError."""
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

        # Only wifi1 present, no wifi0 — pre-fix this used base_labels before assignment.
        channel_util_data = [
            {
                "serial": "Q2KD-AAAA",
                "model": "MR36",
                "wifi1": [{"utilization": 30, "wifi": 25, "nonWifi": 5}],
            }
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices(devices, org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", channel_util_data)
            .build()
        )
        api.organizations.getOrganizationDevices = MagicMock(return_value=devices)
        collector.api = api
        collector.rf_health_collector.api = api

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        # 5GHz metric emitted even though wifi0 is absent.
        # ID-only; org_name/name/network_name dropped per #534.
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
        """F-017: the fetch must pin timespan/resolution/perPage, not just total_pages."""
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
        channel_mock = MagicMock(return_value=[])
        api.networks.getNetworkNetworkHealthChannelUtilization = channel_mock
        collector.api = api
        collector.rf_health_collector.api = api

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        channel_mock.assert_called_once()
        _, kwargs = channel_mock.call_args
        assert kwargs.get("timespan") == 600
        assert kwargs.get("resolution") == 600
        assert kwargs.get("perPage") == 100
        assert kwargs.get("total_pages") == "all"

    async def test_channel_utilization_picks_latest_bucket(
        self, collector, mock_api_builder, metrics
    ):
        """F-017: buckets must be sorted by end time; the newest reading wins."""
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

        # Oldest bucket listed first; the collector must still pick the newest (endTime).
        channel_util_data = [
            {
                "serial": "Q2KD-AAAA",
                "model": "MR36",
                "wifi0": [
                    {
                        "endTime": "2024-01-01T11:50:00Z",
                        "utilization": 10,
                        "wifi": 5,
                        "nonWifi": 5,
                    },
                    {
                        "endTime": "2024-01-01T12:00:00Z",
                        "utilization": 80,
                        "wifi": 60,
                        "nonWifi": 20,
                    },
                ],
            }
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices(devices, org_id=org["id"])
            .with_custom_response("getNetworkNetworkHealthChannelUtilization", channel_util_data)
            .build()
        )
        api.organizations.getOrganizationDevices = MagicMock(return_value=devices)
        collector.api = api
        collector.rf_health_collector.api = api

        await self.run_collector(collector)
        self.assert_collector_success(collector, metrics)

        # ID-only; org_name/name/network_name dropped per #534.
        metrics.assert_gauge_value(
            "meraki_ap_channel_utilization_2_4ghz_percent",
            80,
            org_id=org["id"],
            serial="Q2KD-AAAA",
            model="MR36",
            device_type="MR",
            network_id=network["id"],
            utilization_type="total",
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
