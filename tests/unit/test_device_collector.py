"""Tests for the device collector using test helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.core.error_handling import CollectorError, NothingCollectedError
from meraki_dashboard_exporter.core.metric_expiration import MetricExpirationManager
from meraki_dashboard_exporter.core.org_health import (
    SOURCE_DEVICE,
    SOURCE_ORGANIZATION,
    OrgHealthTracker,
)
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import (
    DeviceFactory,
    DeviceStatusFactory,
    NetworkFactory,
    OrganizationFactory,
)


def _backed_off_tracker(org_id: str) -> OrgHealthTracker:
    """Build a tracker with ``org_id`` driven into backoff (should_collect False)."""
    tracker = OrgHealthTracker()
    for _ in range(tracker.max_consecutive_failures):
        tracker.record_failure(org_id, "Backed Org")
    assert tracker.should_collect(org_id) is False
    return tracker


class TestDeviceCollectorOrgHealthGating(BaseCollectorTest):
    """F-169: DeviceCollector honours the shared OrgHealthTracker per-org gate.

    #509: the backoff check moved from the per-org worker (`_collect_org_devices`)
    into the coordinator's task-creation loop (`_collect_impl`), so gating is now
    exercised through a full `collect()` cycle rather than by calling the worker
    directly.
    """

    collector_class = DeviceCollector

    async def test_backed_off_org_is_skipped(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """A backed-off org's devices are never fetched; a healthy org's are."""
        healthy = OrganizationFactory.create(org_id="HEALTHY")
        backed = OrganizationFactory.create(org_id="BACKED")
        tracker = _backed_off_tracker("BACKED")

        api = (
            mock_api_builder
            .with_organizations([healthy, backed])
            .with_devices([], org_id="HEALTHY")
            .with_devices([], org_id="BACKED")
            .with_device_statuses([], org_id="HEALTHY")
            .with_device_statuses([], org_id="BACKED")
            .build()
        )
        inventory.api = api

        collector = DeviceCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            org_health_tracker=tracker,
        )

        fetched: list[str] = []
        real_fetch_devices = collector._fetch_devices

        async def _spy(org_id: str) -> list:
            fetched.append(org_id)
            return await real_fetch_devices(org_id)

        collector._fetch_devices = _spy  # type: ignore[method-assign]

        await collector.collect()

        assert fetched == ["HEALTHY"]  # BACKED never reached the fetch

    async def test_none_tracker_collects_all(
        self, collector, mock_api_builder, settings, inventory
    ):
        """With no tracker wired in, every org is collected (backward compatible)."""
        assert collector.org_health_tracker is None

        org = OrganizationFactory.create(org_id="ANY")
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_devices([], org_id="ANY")
            .with_device_statuses([], org_id="ANY")
            .build()
        )
        collector.api = api
        collector.inventory.api = api

        fetched: list[str] = []
        real_fetch_devices = collector._fetch_devices

        async def _spy(org_id: str) -> list:
            fetched.append(org_id)
            return await real_fetch_devices(org_id)

        collector._fetch_devices = _spy  # type: ignore[method-assign]

        await collector.collect()

        assert fetched == ["ANY"]


class TestDeviceCollector(BaseCollectorTest):
    """Test DeviceCollector functionality."""

    collector_class = DeviceCollector

    def test_memory_metric_help_states_window(self, collector, metrics):
        """MET-09: device memory used/free HELP must state the 5-min data window.

        collect_memory_metrics (devices/base.py) pins timespan=300, interval=300
        on getOrganizationDevicesSystemMemoryUsageHistoryByInterval and emits the
        single most-recent interval's max/min stat, so the HELP text must say so
        (this is a windowed sample, not an instantaneous reading).
        """
        used = metrics.get_metric("meraki_device_memory_used_bytes")
        free = metrics.get_metric("meraki_device_memory_free_bytes")
        for doc in (used.documentation.lower(), free.documentation.lower()):
            assert "5-min" in doc or "5 min" in doc

    def test_packet_metric_value_retention(self, collector):
        """Test that packet metrics retain last known values."""
        labels = {
            "serial": "Q2KD-XXXX",
            "name": "AP1",
            "network_id": "N_123",
            "network_name": "Test Network",
        }

        # Set initial value for total packet metric
        collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            1000,
        )

        # Verify value was cached
        cache_key = "_mr_packets_downstream_total:name=AP1:network_id=N_123:network_name=Test Network:serial=Q2KD-XXXX"
        assert cache_key in collector._packet_metrics_cache
        assert collector._packet_metrics_cache[cache_key] == 1000

        # Try to set value to 0 (should use cached value)
        collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            0,
        )

        # Value should still be cached as 1000
        assert collector._packet_metrics_cache[cache_key] == 1000

        # Try to set value to None (should use cached value)
        collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            None,
        )

        # Value should still be cached as 1000
        assert collector._packet_metrics_cache[cache_key] == 1000

        # Set a new valid value
        collector._set_packet_metric_value(
            "_mr_packets_downstream_total",
            labels,
            2000,
        )

        # Cache should be updated
        assert collector._packet_metrics_cache[cache_key] == 2000

    def test_packet_loss_metric_allows_zero(self, collector):
        """Test that packet loss metrics allow 0 as a valid value."""
        labels = {
            "serial": "Q2KD-XXXX",
            "name": "AP1",
            "network_id": "N_123",
            "network_name": "Test Network",
        }

        # Set initial value for lost packets
        collector._set_packet_metric_value(
            "_mr_packets_downstream_lost",
            labels,
            10,
        )

        # Setting to 0 should be allowed for "lost" metrics
        collector._set_packet_metric_value(
            "_mr_packets_downstream_lost",
            labels,
            0,
        )

        # Cache should be updated to 0
        cache_key = "_mr_packets_downstream_lost:name=AP1:network_id=N_123:network_name=Test Network:serial=Q2KD-XXXX"
        assert collector._packet_metrics_cache[cache_key] == 0

    async def test_ssid_status_collection(self, collector, mock_api_builder, metrics):
        """Test SSID status metric collection."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")

        # Create SSID status response
        ssid_status_response = [
            {
                "serial": "Q2KD-XXXX",
                "name": "AP1",
                "network": {
                    "id": network["id"],
                    "name": network["name"],
                },
                "basicServiceSets": [
                    {
                        "ssid": {"name": "Guest", "number": 0},
                        "radio": {
                            "isBroadcasting": True,
                            "band": "2.4",
                            "channel": 6,
                            "channelWidth": 20,
                            "power": 15,
                            "index": "0",
                        },
                    },
                    {
                        "ssid": {"name": "Guest", "number": 0},
                        "radio": {
                            "isBroadcasting": True,
                            "band": "5",
                            "channel": 44,
                            "channelWidth": 80,
                            "power": 18,
                            "index": "1",
                        },
                    },
                ],
            }
        ]

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()

        # Manually configure this method because it uses asyncio.to_thread
        # and the mock builder has trouble with wireless organization methods
        api.wireless.getOrganizationWirelessSsidsStatusesByDevice = MagicMock(
            return_value=ssid_status_response
        )

        collector.api = api
        # Also update the MR collector's API reference since it was initialized with the old API
        collector.mr_collector.api = api

        # Create device lookup with device info
        device_lookup = {
            "Q2KD-XXXX": {
                "name": "AP1",
                "model": "MR36",
                "network_id": network["id"],
                "network_name": network["name"],
                "device_type": "MR",
            }
        }

        # Collect SSID status
        await collector.mr_collector.collect_ssid_status(
            org["id"], org.get("name", "Test Org"), device_lookup
        )

        # Verify API was called correctly
        api.wireless.getOrganizationWirelessSsidsStatusesByDevice.assert_called_once_with(
            org["id"],
            perPage=500,
            total_pages="all",
        )

    async def test_ssid_usage_collection(self, collector, mock_api_builder, metrics):
        """Test SSID usage metric collection."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456", name="Test Organization")

        # Create SSID usage response
        ssid_usage_response = [
            {
                "name": "The Cubhouse",
                "usage": {
                    "total": 54878.025390625,
                    "downstream": 10818.2802734375,
                    "upstream": 44059.7451171875,
                    "percentage": 56.01148842015454,
                },
                "clients": {"counts": {"total": 16}},
            },
            {
                "name": "Cubhouse Video",
                "usage": {
                    "total": 42764.8857421875,
                    "downstream": 1053.818359375,
                    "upstream": 41711.0673828125,
                    "percentage": 43.64816127197916,
                },
                "clients": {"counts": {"total": 2}},
            },
            {
                "name": "Cubhouse IOT",
                "usage": {
                    "total": 333.462890625,
                    "downstream": 196.2119140625,
                    "upstream": 137.2509765625,
                    "percentage": 0.3403503078662927,
                },
                "clients": {"counts": {"total": 21}},
            },
        ]

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()

        # Mock the SSID usage API call
        api.organizations.getOrganizationSummaryTopSsidsByUsage = MagicMock(
            return_value=ssid_usage_response
        )

        collector.api = api
        collector.mr_collector.api = api

        # Run the SSID usage collection
        await collector.mr_collector.collect_ssid_usage(org["id"], org["name"])

        # Verify metrics were set correctly
        # First SSID - The Cubhouse
        metrics.assert_gauge_value(
            "meraki_mr_ssid_usage_total_bytes",
            54878.025390625 * 1_000_000,
            org_id="123456",
            ssid="The Cubhouse",
        )

        metrics.assert_gauge_value(
            "meraki_mr_ssid_usage_downstream_bytes",
            10818.2802734375 * 1_000_000,
            org_id="123456",
            ssid="The Cubhouse",
        )

        metrics.assert_gauge_value(
            "meraki_mr_ssid_usage_upstream_bytes",
            44059.7451171875 * 1_000_000,
            org_id="123456",
            ssid="The Cubhouse",
        )

        metrics.assert_gauge_value(
            "meraki_mr_ssid_usage_percent",
            56.01148842015454,
            org_id="123456",
            ssid="The Cubhouse",
        )

        metrics.assert_gauge_value(
            "meraki_mr_ssid_client_count",
            16,
            org_id="123456",
            ssid="The Cubhouse",
        )

        # Second SSID - Cubhouse Video
        metrics.assert_gauge_value(
            "meraki_mr_ssid_usage_total_bytes",
            42764.8857421875 * 1_000_000,
            org_id="123456",
            ssid="Cubhouse Video",
        )

        metrics.assert_gauge_value(
            "meraki_mr_ssid_client_count",
            2,
            org_id="123456",
            ssid="Cubhouse Video",
        )

        # Third SSID - Cubhouse IOT
        metrics.assert_gauge_value(
            "meraki_mr_ssid_usage_total_bytes",
            333.462890625 * 1_000_000,
            org_id="123456",
            ssid="Cubhouse IOT",
        )

        metrics.assert_gauge_value(
            "meraki_mr_ssid_usage_percent",
            0.3403503078662927,
            org_id="123456",
            ssid="Cubhouse IOT",
        )

        metrics.assert_gauge_value(
            "meraki_mr_ssid_client_count",
            21,
            org_id="123456",
            ssid="Cubhouse IOT",
        )

    async def test_ssid_usage_collection_empty_response(self, collector, mock_api_builder, metrics):
        """Test SSID usage metric collection with empty response."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456", name="Test Organization")

        # Configure mock API with empty response
        api = mock_api_builder.with_organizations([org]).build()
        api.organizations.getOrganizationSummaryTopSsidsByUsage = MagicMock(return_value=[])

        collector.api = api
        collector.mr_collector.api = api

        # Run the SSID usage collection - should not raise an exception
        await collector.mr_collector.collect_ssid_usage(org["id"], org["name"])

        # No metrics should be set for empty response

    async def test_ssid_usage_collection_api_error(self, collector, mock_api_builder, metrics):
        """Test SSID usage metric collection handles API errors gracefully."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456", name="Test Organization")

        # Configure mock API to raise an exception
        api = mock_api_builder.with_organizations([org]).build()
        api.organizations.getOrganizationSummaryTopSsidsByUsage = MagicMock(
            side_effect=Exception("API Error")
        )

        collector.api = api
        collector.mr_collector.api = api

        # Run the SSID usage collection - should not raise an exception
        await collector.mr_collector.collect_ssid_usage(org["id"], org["name"])

        # No metrics should be set when API errors occur

    async def test_device_name_lookup(self, collector, mock_api_builder, metrics):
        """Test that device names are correctly looked up from cache."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123")
        devices = [
            DeviceFactory.create_mr(
                serial="Q2KD-XXXX",
                name="Office AP",
                model="MR36",
                network_id=network["id"],
            ),
            DeviceFactory.create_ms(
                serial="Q2SW-XXXX",
                name="Main Switch",
                model="MS120",
                network_id=network["id"],
            ),
        ]

        # Create client overview response
        client_overview_response = [
            {
                "serial": "Q2KD-XXXX",
                "network": {"id": network["id"]},
                "counts": {"byStatus": {"online": 5}},
            }
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices(devices, org_id=org["id"])
            .with_device_statuses([], org_id=org["id"])
            .with_custom_response(
                "getOrganizationWirelessClientsOverviewByDevice", client_overview_response
            )
            .build()
        )
        collector.api = api
        collector.inventory.api = api
        # Update MR collector's API reference
        collector.mr_collector.api = api

        # Collect devices
        await collector._collect_org_devices(org["id"], org.get("name", "Test Org"))

        # Create device lookup manually for testing
        device_lookup = {
            "Q2KD-XXXX": {
                "serial": "Q2KD-XXXX",
                "name": "Office AP",
                "model": "MR36",
                "networkId": network["id"],
                "networkName": network["name"],
            }
        }

        # Collect wireless clients
        await collector.mr_collector.collect_wireless_clients(
            org["id"], org.get("name", "Test Org"), device_lookup
        )

        # Verify API was called
        api.wireless.getOrganizationWirelessClientsOverviewByDevice.assert_called()

    async def test_mr_clients_connected_one_series_per_ap(
        self, collector, mock_api_builder, metrics
    ):
        """#669: meraki_mr_clients_connected must emit one series per AP.

        Regression test for the shared ``device_lookup`` (built in
        ``device.py::_collect_org_devices``) omitting the ``serial`` key. When the
        coordinator built the lookup and fed each entry to
        ``create_device_labels`` via ``collect_wireless_clients``, every AP got
        ``serial=""`` -> identical label sets -> Prometheus collapsed all APs into
        a single aggregated series. This exercises the REAL lookup-building path
        (``_collect_org_devices``), not a hand-built lookup that already carries a
        serial (which is why the sub-collector unit tests never caught this).
        """
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")
        aps = [
            DeviceFactory.create_mr(
                serial="Q2KD-0001", name="AP1", model="MR36", network_id=network["id"]
            ),
            DeviceFactory.create_mr(
                serial="Q2KD-0002", name="AP2", model="MR36", network_id=network["id"]
            ),
            DeviceFactory.create_mr(
                serial="Q2KD-0003", name="AP3", model="MR36", network_id=network["id"]
            ),
        ]
        # Distinct online counts (5 + 3 + 7) so a collapse to one series is
        # unambiguous: the last-written value would win, not the sum.
        client_overview_response = [
            {
                "serial": "Q2KD-0001",
                "network": {"id": network["id"], "name": network["name"]},
                "counts": {"byStatus": {"online": 5}},
            },
            {
                "serial": "Q2KD-0002",
                "network": {"id": network["id"], "name": network["name"]},
                "counts": {"byStatus": {"online": 3}},
            },
            {
                "serial": "Q2KD-0003",
                "network": {"id": network["id"], "name": network["name"]},
                "counts": {"byStatus": {"online": 7}},
            },
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices(aps, org_id=org["id"])
            .with_device_statuses([], org_id=org["id"])
            .with_custom_response(
                "getOrganizationWirelessClientsOverviewByDevice", client_overview_response
            )
            .build()
        )
        collector.api = api
        collector.inventory.api = api
        collector.mr_collector.api = api

        # Real coordinator path: builds device_lookup internally, then runs the
        # MR org-wide block (which includes collect_wireless_clients).
        await collector._collect_org_devices(org["id"], org.get("name", "Test Org"))

        # One distinct series per AP serial. Pre-fix, all three collapsed to a
        # single series with serial="".
        serials = {ls["serial"] for ls in metrics.get_all_label_sets("meraki_mr_clients_connected")}
        assert serials == {"Q2KD-0001", "Q2KD-0002", "Q2KD-0003"}

        metrics.assert_gauge_value("meraki_mr_clients_connected", 5, serial="Q2KD-0001")
        metrics.assert_gauge_value("meraki_mr_clients_connected", 3, serial="Q2KD-0002")
        metrics.assert_gauge_value("meraki_mr_clients_connected", 7, serial="Q2KD-0003")

    def test_get_device_type(self, collector):
        """Test device type extraction from model."""
        assert collector._get_device_type({"model": "MR36"}) == "MR"
        assert collector._get_device_type({"model": "MS120-8"}) == "MS"
        assert collector._get_device_type({"model": "MT10"}) == "MT"
        assert collector._get_device_type({"model": "MX64"}) == "MX"
        assert collector._get_device_type({"model": "Z"}) == "Unknown"
        assert collector._get_device_type({}) == "Unknown"

    async def test_ssid_status_with_duplicate_radios(self, collector, mock_api_builder, metrics):
        """Test that SSID status handles duplicate radios correctly."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")

        # Create SSID status response with multiple SSIDs on same radio
        ssid_status_response = [
            {
                "serial": "Q2KD-XXXX",
                "name": "AP1",
                "network": {
                    "id": network["id"],
                    "name": network["name"],
                },
                "basicServiceSets": [
                    {
                        "ssid": {"name": "Guest", "number": 0},
                        "radio": {
                            "isBroadcasting": True,
                            "band": "2.4",
                            "channel": 6,
                            "channelWidth": 20,
                            "power": 15,
                            "index": "0",
                        },
                    },
                    {
                        "ssid": {"name": "Corporate", "number": 1},
                        "radio": {
                            "isBroadcasting": True,
                            "band": "2.4",
                            "channel": 6,
                            "channelWidth": 20,
                            "power": 15,
                            "index": "0",
                        },
                    },
                ],
            }
        ]

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()

        # Manually configure wireless method
        api.wireless.getOrganizationWirelessSsidsStatusesByDevice = MagicMock(
            return_value=ssid_status_response
        )

        collector.api = api
        collector.mr_collector.api = api

        # Create device lookup with device info
        device_lookup = {
            "Q2KD-XXXX": {
                "name": "AP1",
                "model": "MR36",
                "network_id": network["id"],
                "network_name": network["name"],
                "device_type": "MR",
            }
        }

        # Collect SSID status
        await collector.mr_collector.collect_ssid_status(
            org["id"], org.get("name", "Test Org"), device_lookup
        )

        # The collector should only process each radio once
        # This test verifies the method completes without duplicate processing

    def test_device_status_info_clears_stale_labels(self, collector):
        """Test that stale device status label series are removed on status change.

        When a device transitions (e.g. online -> offline), the old label
        series with status="online" must be removed so only the current
        status is reported.
        """
        device = {
            "serial": "Q2AB-1234",
            "name": "Test Device",
            "model": "MR36",
            "networkId": "N_111",
            "networkName": "Test Network",
            "availability_status": "online",
        }

        # First collection: device is online
        collector._collect_common_metrics(device, org_id="org1", org_name="Test Org")

        # Verify the "online" status entry exists
        gauge = collector._device_status_info
        assert len(gauge._metrics) == 1

        # Second collection: device transitions to offline
        device["availability_status"] = "offline"
        collector._collect_common_metrics(device, org_id="org1", org_name="Test Org")

        # Should have exactly 1 entry (offline), not 2 (online + offline)
        assert len(gauge._metrics) == 1
        # Verify the remaining entry has status="offline"
        label_tuple = list(gauge._metrics.keys())[0]
        # Status is the last label in the labelnames list
        assert label_tuple[-1] == "offline"

    def test_device_up_labels_are_id_only(self, collector):
        """#534: meraki_device_up carries stable IDs only, no mutable names.

        org_name/network_name/name join via meraki_org_info/meraki_network_info/
        meraki_device_status_info respectively - they must not be re-added here.
        """
        assert set(collector._device_up._labelnames) == {
            "org_id",
            "network_id",
            "serial",
            "model",
            "device_type",
        }

    def test_device_status_info_keeps_name_drops_org_network_names(self, collector):
        """#534: meraki_device_status_info is the designated device-name carrier.

        It keeps `name` (per docs/stability.md) but drops org_name/network_name -
        those join via meraki_org_info/meraki_network_info on org_id/network_id.
        """
        assert set(collector._device_status_info._labelnames) == {
            "org_id",
            "network_id",
            "serial",
            "name",
            "model",
            "device_type",
            "status",
        }

    def test_device_memory_metrics_labels_are_id_only(self, collector):
        """#534: memory metrics carry stable IDs only, no mutable names."""
        base_labels = {"org_id", "network_id", "serial", "model", "device_type"}
        assert set(collector._device_memory_used_bytes._labelnames) == base_labels | {"stat"}
        assert set(collector._device_memory_free_bytes._labelnames) == base_labels | {"stat"}
        assert set(collector._device_memory_total_bytes._labelnames) == base_labels
        assert set(collector._device_memory_usage_percent._labelnames) == base_labels

    def test_device_status_info_status_labels_include_name(self, collector):
        """The status_labels dict built at emission time must include `name`.

        Regression guard: create_device_labels() no longer emits `name` (#534),
        so _collect_common_metrics must pass it explicitly as an extra label or
        the KEEP name carrier would silently lose its device-name value.
        """
        device = {
            "serial": "Q2AB-5678",
            "name": "Named Device",
            "model": "MS120-8",
            "networkId": "N_222",
            "networkName": "Test Network 2",
            "availability_status": "online",
        }
        collector._collect_common_metrics(device, org_id="org2", org_name="Test Org 2")

        gauge = collector._device_status_info
        label_tuple = next(iter(gauge._metrics.keys()))
        labelnames = gauge._labelnames
        labels = dict(zip(labelnames, label_tuple, strict=True))
        assert labels["name"] == "Named Device"
        assert labels["serial"] == "Q2AB-5678"
        assert "org_name" not in labels
        assert "network_name" not in labels

    async def test_device_collection_basic(self, collector, mock_api_builder, metrics):
        """Test basic device collection functionality."""
        # Set up standard test data
        test_data = self.setup_standard_test_data(mock_api_builder)
        # Availabilities must be explicitly configured or the mock returns an
        # unconfigured MagicMock, which now raises DataValidationError (#509
        # exposed this pre-existing test-fixture gap once org failures stopped
        # being silently swallowed).
        for org in test_data["organizations"]:
            mock_api_builder.with_device_statuses([], org_id=org["id"])
        collector.api = mock_api_builder.build()

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

        # Verify API calls were tracked
        self.assert_api_call_tracked(collector, metrics, "getOrganizationDevices", count=1)

    async def test_catalyst_switch_triggers_ms_specific_metrics(
        self, collector, mock_api_builder, metrics
    ):
        """A Meraki-managed Catalyst switch must still trigger the MS org-wide block.

        Catalyst switches report productType == "switch" but their model does not
        start with "MS" (e.g. "C9300-48P"). The MS-specific org-wide block (STP
        priorities, switch-stack metrics, and the PSU/power-supply collector) must
        still run for an org containing ONLY such devices - regression test for
        F-030 (the gate previously only matched a model.startswith("MS") prefix).
        """
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")
        catalyst_switch = DeviceFactory.create(
            serial="Q2CAT-0001",
            name="Catalyst Switch",
            model="C9300-48P",
            productType="switch",
            network_id=network["id"],
        )

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([catalyst_switch], org_id=org["id"])
            .with_device_statuses([], org_id=org["id"])
            .build()
        )
        collector.api = api
        collector.inventory.api = api
        collector.ms_collector.api = api
        collector.ms_stack_collector.api = api
        collector.ms_power_collector.api = api

        # The device type gets remapped to MS via the productType override
        # (_get_device_type), so the per-device MS path already worked before
        # F-030; what's under test here is only the org-wide gate.
        collector._collect_ms_specific_metrics = AsyncMock(
            wraps=collector._collect_ms_specific_metrics
        )

        await collector._collect_org_devices(org["id"], org.get("name", "Test Org"))

        collector._collect_ms_specific_metrics.assert_called_once()

    async def test_catalyst_ap_triggers_mr_specific_metrics(
        self, collector, mock_api_builder, metrics
    ):
        """A Catalyst CW* access point must still trigger the MR org-wide block.

        Catalyst APs report productType == "wireless" but their model does not
        start with "MR" (e.g. "CW9166I"). The MR-specific org-wide block must
        still run for an org containing ONLY such devices - regression test for
        #624 (the gate previously only matched a model.startswith("MR") prefix).
        """
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")
        catalyst_ap = DeviceFactory.create(
            serial="Q2CW-0001",
            name="Catalyst AP",
            model="CW9166I",
            productType="wireless",
            network_id=network["id"],
        )

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([catalyst_ap], org_id=org["id"])
            .with_device_statuses([], org_id=org["id"])
            .build()
        )
        collector.api = api
        collector.inventory.api = api

        collector._collect_mr_specific_metrics = AsyncMock(
            wraps=collector._collect_mr_specific_metrics
        )

        await collector._collect_org_devices(org["id"], org.get("name", "Test Org"))

        collector._collect_mr_specific_metrics.assert_called_once()

    async def test_mr_subcollection_failure_increments_error_counter(self, collector, metrics):
        """RES-04/#511: a tolerated MR sub-collection failure must increment error metrics.

        `meraki_exporter_collector_errors_total` must increment, not just
        log-and-swallow silently. `_collect_mr_specific_metrics` wraps each MR sub-collection call in its
        own try/except that logs and continues (never raises), so a broken
        SSID-usage fetch must neither abort the other MR sub-collections nor
        disappear from the exporter's own error metrics.
        """
        collector.inventory = None  # skip the networks fetch, irrelevant here
        collector.mr_collector.collect_ssid_usage = AsyncMock(
            side_effect=Exception("500 Internal Server Error")
        )

        # Must not raise - a single MR sub-collection failure is tolerated.
        await collector._collect_mr_specific_metrics("123456", "Test Org", [], {})

        self.assert_collector_error(collector, metrics, error_type="unknown")

    async def test_org_devices_top_level_failure_increments_error_counter(
        self, collector, mock_api_builder, metrics
    ):
        """RES-04/#511: the top-level catch-all must also increment the error counter.

        `_collect_org_devices`'s top-level catch-all must increment the error
        counter, not just log the exception. This is the outermost tolerated
        swallow for the per-org device worker:
        any unexpected (non-CollectorError) exception reaching it is logged and
        swallowed without failing the org's device-domain health verdict, so it
        must remain observable via the error counter.
        """
        org = OrganizationFactory.create(org_id="654321", name="Test Org")
        api = mock_api_builder.with_organizations([org]).build()
        collector.api = api

        async def _boom(_org_id: str) -> None:
            raise Exception("unexpected failure")

        collector._fetch_networks_for_poe = _boom  # type: ignore[method-assign]

        # The devices fetch itself must succeed so we reach the code past it.
        collector._fetch_devices = AsyncMock(
            return_value=[
                DeviceFactory.create(serial="Q2XX-0001", model="MR36", network_id="N_1"),
            ]
        )
        collector._fetch_device_availabilities = AsyncMock(return_value=[])

        # Must not raise - this is a tolerated (not a CollectorError) failure.
        await collector._collect_org_devices(org["id"], org["name"])

        self.assert_collector_error(collector, metrics, error_type="unknown")


class TestDeviceCollectorNothingCollected(BaseCollectorTest):
    """#509: total collection failure must raise instead of being swallowed.

    Base settings are multi-org (no ``settings.meraki.org_id`` configured), so
    ``getOrganizations`` errors raise straight through
    ``OrganizationInventory.get_organizations`` rather than being replaced with
    a single-org placeholder.
    """

    collector_class = DeviceCollector

    async def test_org_fetch_failure_raises(self, collector, mock_api_builder):
        """A hard failure fetching organizations must raise, not swallow."""
        api = mock_api_builder.with_error("getOrganizations", Exception("Connection error")).build()
        collector.api = api
        collector.inventory.api = api

        with pytest.raises(CollectorError):
            await collector.collect()

    async def test_all_orgs_failed_raises_nothing_collected(self, collector, mock_api_builder):
        """Every org's primary fetch failing must raise NothingCollectedError."""
        org = OrganizationFactory.create(org_id="123456")
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_error("getOrganizationDevices", Exception("Connection error"))
            .build()
        )
        collector.api = api
        collector.inventory.api = api

        with pytest.raises(NothingCollectedError):
            await collector.collect()

    async def test_partial_org_failure_does_not_raise(self, collector, mock_api_builder, metrics):
        """One org failing while another succeeds must NOT raise (partial success)."""
        healthy_org = OrganizationFactory.create(org_id="HEALTHY")
        broken_org = OrganizationFactory.create(org_id="BROKEN")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")
        device = DeviceFactory.create_mr(
            serial="Q2KD-XXXX",
            name="Healthy AP",
            network_id=network["id"],
        )

        api = (
            mock_api_builder
            .with_organizations([healthy_org, broken_org])
            .with_networks([network], org_id="HEALTHY")
            .with_devices([device], org_id="HEALTHY")
            .with_device_statuses(
                [DeviceStatusFactory.create(serial="Q2KD-XXXX", status="online")], org_id="HEALTHY"
            )
            .with_error("getOrganizationDevices", Exception("Connection error"), org_id="BROKEN")
            .build()
        )
        collector.api = api
        collector.inventory.api = api

        await collector.collect()

        metrics.assert_gauge_value("meraki_device_up", 1, serial="Q2KD-XXXX")

    async def test_all_orgs_in_backoff_raises(self, collector, mock_api_builder):
        """Every org skipped for backoff must raise NothingCollectedError (not a spurious success)."""
        org = OrganizationFactory.create(org_id="BACKED")
        api = mock_api_builder.with_organizations([org]).build()
        collector.api = api
        collector.inventory.api = api
        collector.org_health_tracker = _backed_off_tracker("BACKED")

        with pytest.raises(NothingCollectedError) as exc_info:
            await collector.collect()

        assert exc_info.value.skipped_backoff == 1
        assert exc_info.value.failed == 0

    async def test_empty_org_list_is_success(self, collector, mock_api_builder, metrics):
        """An empty (but successfully fetched) org list is a legitimate no-op success."""
        api = mock_api_builder.with_organizations([]).build()
        collector.api = api
        collector.inventory.api = api

        await collector.collect()

        self.assert_collector_success(collector, metrics)


class TestDeviceCollectorOrgHealthReporting(BaseCollectorTest):
    """#547: DeviceCollector reports its per-org verdict into the shared tracker.

    Verdicts are recorded under the SOURCE_DEVICE failure domain so a device
    endpoint failing engages backoff for that org even when the organization
    collector reports success or is disabled entirely; a device recovery clears
    it. The verdict mirrors the coordinator's raise/return accounting: the worker
    raises (CollectorError) only when the device fetch fails; any normal or
    swallowed-error return is a device-domain success.
    """

    collector_class = DeviceCollector

    async def test_successful_org_records_device_success(self, collector):
        """A healthy per-org cycle records a SOURCE_DEVICE success."""
        tracker = OrgHealthTracker(max_consecutive_failures=3)
        collector.org_health_tracker = tracker
        # Empty device list is a legitimate no-op success for the worker.
        collector._fetch_devices = AsyncMock(return_value=[])  # type: ignore[method-assign]

        await collector._collect_org_devices("ORG1", "Org One")

        health = tracker.get_health("ORG1")
        assert health is not None
        assert health.source_failures.get(SOURCE_DEVICE) == 0
        assert health.last_success > 0
        assert tracker.should_collect("ORG1") is True

    async def test_device_failure_engages_backoff_when_org_disabled(self, collector):
        """A persistent device-only failure engages backoff (#547 cases 1 and 2).

        The organization collector never writes into the tracker, yet backoff
        still engages for the org from the device domain alone.
        """
        tracker = OrgHealthTracker(max_consecutive_failures=3)
        collector.org_health_tracker = tracker
        # Fetch failure -> worker raises CollectorError -> device-domain failure.
        collector._fetch_devices = AsyncMock(return_value=None)  # type: ignore[method-assign]

        for _ in range(3):
            with pytest.raises(CollectorError):
                await collector._collect_org_devices("ORG1", "Org One")

        health = tracker.get_health("ORG1")
        assert health.source_failures[SOURCE_DEVICE] == 3
        # Org collector disabled: it contributed no failures of its own.
        assert SOURCE_ORGANIZATION not in health.source_failures
        assert tracker.should_collect("ORG1") is False

    async def test_device_recovery_clears_backoff(self, collector):
        """(3): once the device domain recovers, backoff clears."""
        tracker = OrgHealthTracker(max_consecutive_failures=3)
        collector.org_health_tracker = tracker
        collector._fetch_devices = AsyncMock(return_value=None)  # type: ignore[method-assign]
        for _ in range(3):
            with pytest.raises(CollectorError):
                await collector._collect_org_devices("ORG1", "Org One")
        assert tracker.should_collect("ORG1") is False

        # A healthy cycle recorded directly by the worker clears the backoff.
        collector._fetch_devices = AsyncMock(return_value=[])  # type: ignore[method-assign]
        await collector._collect_org_devices("ORG1", "Org One")
        assert tracker.should_collect("ORG1") is True
        assert tracker.get_health("ORG1").consecutive_failures == 0

    async def test_none_tracker_is_noop(self, collector):
        """With no tracker wired, the worker records nothing (backward compatible)."""
        assert collector.org_health_tracker is None
        collector._fetch_devices = AsyncMock(return_value=[])  # type: ignore[method-assign]
        # Must not raise despite there being no tracker to record into.
        await collector._collect_org_devices("ORG1", "Org One")


def _device_up_samples(registry) -> dict[tuple, float]:
    """Return {sorted-label-tuple: value} for every meraki_device_up series."""
    out: dict[tuple, float] = {}
    for family in registry.collect():
        if family.name == "meraki_device_up":
            for sample in family.samples:
                out[tuple(sorted(sample.labels.items()))] = sample.value
    return out


class TestWebhookDeviceStateApplier(BaseCollectorTest):
    """#614: DeviceCollector.apply_webhook_device_state fast-path flip.

    The poll owns meraki_device_up; the webhook may only accelerate a DOWN
    transition by writing the exact same-labelled series via the same
    _set_metric path (same collector identity + TTL), never a novel series.
    """

    collector_class = DeviceCollector

    SERIAL = "Q2AA-BBBB-CCCC"

    def _build_online_api(self, mock_api_builder, *, status: str = "online"):
        """Build a mock API for one MR device at ``status`` in org ORG1."""
        org = OrganizationFactory.create(org_id="ORG1")
        network = NetworkFactory.create(network_id="N_1", name="Net")
        device = DeviceFactory.create_mr(serial=self.SERIAL, name="AP1", network_id="N_1")
        return (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id="ORG1")
            .with_devices([device], org_id="ORG1")
            .with_device_statuses(
                [DeviceStatusFactory.create(serial=self.SERIAL, status=status)],
                org_id="ORG1",
            )
            .build()
        )

    async def test_webhook_down_flip_before_next_poll(self, collector, mock_api_builder, metrics):
        """Test 1: a poll seeds device_up=1; a webhook flip drops it to 0."""
        collector.api = self._build_online_api(mock_api_builder)
        await self.run_collector(collector)
        metrics.assert_gauge_value("meraki_device_up", 1, serial=self.SERIAL)

        assert collector.apply_webhook_device_state(self.SERIAL, up=False) is True
        metrics.assert_gauge_value("meraki_device_up", 0, serial=self.SERIAL)

    async def test_poll_reasserts_truth_after_flip(self, collector, mock_api_builder, metrics):
        """Test 2: the next poll re-asserts polled truth over a webhook write."""
        collector.api = self._build_online_api(mock_api_builder)
        await self.run_collector(collector)

        # Wrong/spurious webhook: mark an online device down.
        assert collector.apply_webhook_device_state(self.SERIAL, up=False) is True
        metrics.assert_gauge_value("meraki_device_up", 0, serial=self.SERIAL)

        # Next poll (device still online) corrects it back to 1.
        await self.run_collector(collector)
        metrics.assert_gauge_value("meraki_device_up", 1, serial=self.SERIAL)

    async def test_flip_creates_no_duplicate_series(
        self, collector, mock_api_builder, metrics, isolated_registry
    ):
        """Test 3: the flip mutates the poll's series in place, adds no series."""
        collector.api = self._build_online_api(mock_api_builder)
        await self.run_collector(collector)

        before = _device_up_samples(isolated_registry)
        assert collector.apply_webhook_device_state(self.SERIAL, up=False) is True
        after = _device_up_samples(isolated_registry)

        # Same set of label tuples, same count — no duplicate/relabelled series.
        assert set(before) == set(after)
        assert len(after) == len(before)

        # The flipped sample carries EXACTLY the poll-owned label dict, now at 0.
        poll_labels = collector._webhook_device_labels[self.SERIAL]
        key = tuple(sorted(poll_labels.items()))
        assert after[key] == 0.0
        # And that label dict is the byte-identical create_device_labels output.
        assert poll_labels["serial"] == self.SERIAL

    async def test_unknown_serial_is_noop(
        self, collector, mock_api_builder, metrics, isolated_registry
    ):
        """Test 4 (applier side): unknown serial returns False, touches nothing."""
        collector.api = self._build_online_api(mock_api_builder)
        await self.run_collector(collector)

        before = _device_up_samples(isolated_registry)
        assert collector.apply_webhook_device_state("NOPE-NOPE-NOPE", up=False) is False
        after = _device_up_samples(isolated_registry)
        assert before == after  # values and series identical

    async def test_expiration_tracking_identity(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """Test 7: a webhook flip refreshes the poll's tracking entry, not a 2nd.

        Exactly one (collector, meraki_device_up, labels) tracking entry exists,
        and its per-series TTL equals the device_availability group TTL.
        """
        expiration_manager = MetricExpirationManager(settings=settings)
        api = self._build_online_api(mock_api_builder)
        collector = DeviceCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            expiration_manager=expiration_manager,
        )
        inventory.api = api
        await collector.collect()

        def _device_up_keys():
            return [
                key for key in expiration_manager._metric_timestamps if key[1] == "meraki_device_up"
            ]

        assert len(_device_up_keys()) == 1
        collector.apply_webhook_device_state(self.SERIAL, up=False)
        keys = _device_up_keys()
        assert len(keys) == 1  # refreshed, not duplicated

        entry = expiration_manager._metric_timestamps[keys[0]]
        assert entry.ttl_seconds == collector._group_ttl_seconds(
            EndpointGroupName.DEVICE_AVAILABILITY
        )

    async def test_pruning_removed_device(self, collector, mock_api_builder, metrics):
        """Test 8: a device dropped from a later poll becomes a webhook no-op.

        The per-org atomic rebind drops prior entries owned by the org and merges
        the fresh set, so a serial absent from a later (still non-empty) poll is
        pruned from the map.
        """
        collector.api = self._build_online_api(mock_api_builder)
        await self.run_collector(collector)
        assert self.SERIAL in collector._webhook_device_labels

        # Next poll for the same org returns a DIFFERENT device -> old serial pruned.
        org = OrganizationFactory.create(org_id="ORG1")
        network = NetworkFactory.create(network_id="N_1", name="Net")
        other = DeviceFactory.create_mr(serial="Q2ZZ-ZZZZ-ZZZZ", name="AP2", network_id="N_1")
        replaced_api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([network], org_id="ORG1")
            .with_devices([other], org_id="ORG1")
            .with_device_statuses(
                [DeviceStatusFactory.create(serial="Q2ZZ-ZZZZ-ZZZZ", status="online")],
                org_id="ORG1",
            )
            .build()
        )
        collector.api = replaced_api
        # Drop the inventory device cache so the second poll sees the new device
        # list (get_devices is cached; a real removed-device poll would refetch).
        await collector.inventory.invalidate()
        await self.run_collector(collector)

        assert self.SERIAL not in collector._webhook_device_labels
        assert "Q2ZZ-ZZZZ-ZZZZ" in collector._webhook_device_labels
        assert collector.apply_webhook_device_state(self.SERIAL, up=False) is False

    async def test_concurrency_smoke_flip_interleaved_with_poll(
        self, collector, mock_api_builder, metrics, isolated_registry
    ):
        """Test 9: flips fired concurrently with a poll never raise; count stable."""
        collector.api = self._build_online_api(mock_api_builder)
        await self.run_collector(collector)

        async def _flip(up: bool) -> None:
            collector.apply_webhook_device_state(self.SERIAL, up=up)

        # Interleave a poll cycle with a burst of flips on the same event loop.
        await asyncio.gather(
            self.run_collector(collector),
            _flip(False),
            _flip(False),
            _flip(True),
        )

        samples = _device_up_samples(isolated_registry)
        # Exactly one device_up series for the serial (no duplication under races).
        serial_series = [v for k, v in samples.items() if ("serial", self.SERIAL) in k]
        assert len(serial_series) == 1
        # Final value is a valid 0/1 written by the last writer (poll or flip).
        assert serial_series[0] in {0.0, 1.0}
