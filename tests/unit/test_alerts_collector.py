"""Tests for the AlertsCollector using test helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from meraki_dashboard_exporter.collectors import alerts as alerts_module
from meraki_dashboard_exporter.collectors.alerts import AlertsCollector
from meraki_dashboard_exporter.core.batch_processing import process_in_batches_with_errors
from meraki_dashboard_exporter.core.constants import AlertMetricName, UpdateTier
from meraki_dashboard_exporter.core.org_health import OrgHealthTracker
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import AlertFactory, DeviceFactory, NetworkFactory, OrganizationFactory
from tests.helpers.metrics import MetricAssertions


def _backed_off_tracker(org_id: str) -> OrgHealthTracker:
    """Build a tracker with ``org_id`` driven into backoff (should_collect False)."""
    tracker = OrgHealthTracker()
    for _ in range(tracker.max_consecutive_failures):
        tracker.record_failure(org_id, "Backed Org")
    assert tracker.should_collect(org_id) is False
    return tracker


class TestAlertsCollectorOrgHealthGating(BaseCollectorTest):
    """F-169: AlertsCollector honours the shared OrgHealthTracker per-org gate."""

    collector_class = AlertsCollector
    update_tier = UpdateTier.MEDIUM

    async def test_backed_off_org_is_skipped(
        self, mock_api, settings, isolated_registry, inventory
    ):
        """A backed-off org is skipped before the alerts API call; a healthy org is not."""
        tracker = _backed_off_tracker("BACKED")
        collector = AlertsCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            org_health_tracker=tracker,
        )
        api_call = MagicMock(return_value=[])
        collector.api.organizations.getOrganizationAssuranceAlerts = api_call

        await collector._collect_org_alerts("BACKED", "Backed Org")
        assert api_call.call_count == 0  # gate short-circuited before the API call

        await collector._collect_org_alerts("HEALTHY", "Healthy Org")
        assert api_call.call_count == 1

    async def test_none_tracker_collects_all(self, collector):
        """With no tracker wired in, every org is collected (backward compatible)."""
        assert collector.org_health_tracker is None
        api_call = MagicMock(return_value=[])
        collector.api.organizations.getOrganizationAssuranceAlerts = api_call

        await collector._collect_org_alerts("ANY", "Any Org")
        assert api_call.call_count == 1


class TestAlertsCollector(BaseCollectorTest):
    """Test AlertsCollector functionality."""

    collector_class = AlertsCollector
    update_tier = UpdateTier.MEDIUM

    async def test_collect_with_no_alerts(self, collector, mock_api_builder, metrics):
        """Test collection when no alerts are present."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAssuranceAlerts", [])
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

        # The getOrganization call now goes through the inventory cache, so it's not tracked
        # directly by the collector. Only the alerts API call is tracked.
        self.assert_api_call_tracked(collector, metrics, "getOrganizationAssuranceAlerts")

        # Verify no alerts metrics were set
        # The collector doesn't set a metric for 0 alerts, it clears them
        # So we should check that the metric is not set
        metrics.assert_metric_not_set(AlertMetricName.ALERTS_ACTIVE)

    async def test_collect_with_active_alerts(self, collector, mock_api_builder, metrics):
        """Test collection with active alerts."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")

        alerts = [
            AlertFactory.create(
                alert_id="alert1",
                alert_type="connectivity",
                categoryType="network",
                severity="critical",
                deviceType="MR",
                network=network,
                dismissedAt=None,
                resolvedAt=None,
            ),
            AlertFactory.create(
                alert_id="alert2",
                alert_type="performance",
                categoryType="wireless",
                severity="warning",
                deviceType="MS",
                network=network,
                dismissedAt=None,
                resolvedAt=None,
            ),
            AlertFactory.create(
                alert_id="alert3",
                alert_type="security",
                categoryType="security",
                severity="informational",
                deviceType=None,  # Organization-wide alert
                network=NetworkFactory.create(network_id="N_456", name="Another Network"),
                dismissedAt=None,
                resolvedAt=None,
            ),
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAssuranceAlerts", alerts)
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)
        self.assert_api_call_tracked(collector, metrics, "getOrganizationAssuranceAlerts")

        # Verify alert metrics
        # The active alerts metric is set per alert type/severity combination, not as a total
        # We should check for the specific alert combinations

        # Verify type-specific metrics
        metrics.assert_gauge_value(
            AlertMetricName.ALERTS_ACTIVE,
            1,
            org_id="123",
            org_name="Test Org",
            alert_type="connectivity",
            category_type="network",
            severity="critical",
            device_type="MR",
            network_id="N_123",
            network_name="Test Network",
        )

        # Verify summary metrics
        metrics.assert_gauge_value(
            AlertMetricName.ALERTS_TOTAL_BY_SEVERITY,
            1,
            org_id="123",
            org_name="Test Org",
            severity="critical",
        )
        metrics.assert_gauge_value(
            AlertMetricName.ALERTS_TOTAL_BY_SEVERITY,
            1,
            org_id="123",
            org_name="Test Org",
            severity="warning",
        )

    async def test_collect_skips_dismissed_alerts(self, collector, mock_api_builder, metrics):
        """Test that dismissed alerts are skipped."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")

        alerts = [
            AlertFactory.create(
                alert_id="alert1",
                dismissedAt="2024-01-01T00:00:00Z",  # Dismissed
                resolvedAt=None,
                network=network,
            ),
            AlertFactory.create(
                alert_id="alert2",
                dismissedAt=None,
                resolvedAt="2024-01-01T00:00:00Z",  # Resolved
                network=network,
            ),
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAssuranceAlerts", alerts)
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

        # Verify no active alerts (both were dismissed/resolved)
        # The collector clears metrics when no alerts exist
        metrics.assert_metric_not_set(AlertMetricName.ALERTS_ACTIVE)

    async def test_collect_handles_api_404_error(self, collector, mock_api_builder, metrics):
        """Test handling of 404 errors (alerts API not available)."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Configure mock API with 404 error
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_error("getOrganizationAssuranceAlerts", 404)
            .build()
        )
        collector.api = api

        # Run collection - should handle error gracefully
        await self.run_collector(collector)

        # Verify collector still succeeded (404 is handled gracefully)
        self.assert_collector_success(collector, metrics)
        self.assert_api_call_tracked(collector, metrics, "getOrganizationAssuranceAlerts")

    async def test_collect_with_specific_org_id(
        self, mock_api_builder, settings, isolated_registry
    ):
        """Test collection with a specific org_id configured."""
        # Configure specific org_id
        settings.meraki.org_id = "456"

        # Create collector with specific settings
        collector = AlertsCollector(
            api=mock_api_builder.build(), settings=settings, registry=isolated_registry
        )

        # Configure mock API
        api = mock_api_builder.with_custom_response("getOrganizationAssuranceAlerts", []).build()
        collector.api = api

        # Run collection
        await collector.collect()

        # Create metrics helper
        metrics = MetricAssertions(isolated_registry)

        # Should not call getOrganizations (org_id is specified)
        # Should call alerts API with configured org_id
        self.assert_api_call_tracked(collector, metrics, "getOrganizationAssuranceAlerts")

    async def test_collect_handles_missing_network_data(self, collector, mock_api_builder, metrics):
        """Test handling of alerts with missing network data."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Create alerts with missing network data
        alert1 = AlertFactory.create(alert_id="alert1", dismissedAt=None, resolvedAt=None)
        alert1["network"] = {}  # Empty network data

        alert2 = AlertFactory.create(alert_id="alert2", dismissedAt=None, resolvedAt=None)
        if "network" in alert2:
            del alert2["network"]  # Missing network key entirely

        alerts = [alert1, alert2]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAssuranceAlerts", alerts)
            .build()
        )
        collector.api = api

        # Run collection - should handle missing data gracefully
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

    async def test_collect_handles_general_exception(self, collector, mock_api_builder, metrics):
        """Test handling of general exceptions during collection."""
        # Configure mock API to raise exception
        api = mock_api_builder.with_error("getOrganizations", Exception("Network error")).build()
        collector.api = api

        # Run collection - should handle error gracefully (AlertsCollector has error handling decorators)
        await self.run_collector(collector, expect_success=True)

        # The collector should complete successfully but log the error

    def test_update_tier(self, collector):
        """Test that alerts collector has correct update tier."""
        assert collector.update_tier == UpdateTier.MEDIUM
        assert self.update_tier == UpdateTier.MEDIUM

    async def test_collect_sensor_alerts(self, collector, mock_api_builder, metrics):
        """Test collection of sensor alert metrics."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        networks = [
            NetworkFactory.create(network_id="N_123", name="Test Network 1"),
            NetworkFactory.create(network_id="N_456", name="Test Network 2"),
        ]
        # Need sensor devices for network filtering to include networks for sensor alerts
        sensor_devices = [
            DeviceFactory.create_mt(
                network_id="N_123", productType="sensor", serial="Q2MT-XXXX-0001"
            ),
            DeviceFactory.create_mt(
                network_id="N_456", productType="sensor", serial="Q2MT-XXXX-0002"
            ),
        ]

        # Create sensor alert response data
        sensor_alert_response_1 = [
            {
                "startTs": "2025-07-21T18:00:00Z",
                "endTs": "2025-07-21T18:59:59Z",
                "counts": {
                    "apparentPower": 0,
                    "co2": 2,
                    "current": 0,
                    "door": 5,
                    "frequency": 0,
                    "humidity": 1,
                    "indoorAirQuality": 0,
                    "noise": {"ambient": 3},
                    "pm25": 0,
                    "powerFactor": 0,
                    "realPower": 0,
                    "temperature": 7,
                    "tvoc": 0,
                    "upstreamPower": 0,
                    "voltage": 0,
                    "water": 1,
                },
            }
        ]

        sensor_alert_response_2 = [
            {
                "startTs": "2025-07-21T18:00:00Z",
                "endTs": "2025-07-21T18:59:59Z",
                "counts": {
                    "apparentPower": 1,
                    "co2": 0,
                    "current": 2,
                    "door": 0,
                    "frequency": 0,
                    "humidity": 0,
                    "indoorAirQuality": 0,
                    "noise": {"ambient": 0},
                    "pm25": 0,
                    "powerFactor": 0,
                    "realPower": 3,
                    "temperature": 0,
                    "tvoc": 0,
                    "upstreamPower": 0,
                    "voltage": 1,
                    "water": 0,
                },
            }
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_devices(sensor_devices, org_id="123")
            .with_custom_response("getOrganizationAssuranceAlerts", [])
            .with_custom_response("getOrganizationNetworks", networks)
            .build()
        )

        # Set up network-specific responses with side effects based on the network_id parameter
        def get_sensor_alerts(network_id, **kwargs):
            if network_id == "N_123":
                return sensor_alert_response_1
            elif network_id == "N_456":
                return sensor_alert_response_2
            else:
                return []

        api.sensor.getNetworkSensorAlertsOverviewByMetric = MagicMock(side_effect=get_sensor_alerts)
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

        # Verify sensor alert metrics for network 1
        metrics.assert_gauge_value(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            2,
            network_id="N_123",
            network_name="Test Network 1",
            metric="co2",
        )
        metrics.assert_gauge_value(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            5,
            network_id="N_123",
            network_name="Test Network 1",
            metric="door",
        )
        metrics.assert_gauge_value(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            7,
            network_id="N_123",
            network_name="Test Network 1",
            metric="temperature",
        )
        metrics.assert_gauge_value(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            1,
            network_id="N_123",
            network_name="Test Network 1",
            metric="water",
        )
        metrics.assert_gauge_value(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            3,
            network_id="N_123",
            network_name="Test Network 1",
            metric="noise_ambient",
        )

        # Verify sensor alert metrics for network 2
        metrics.assert_gauge_value(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            1,
            network_id="N_456",
            network_name="Test Network 2",
            metric="apparentPower",
        )
        metrics.assert_gauge_value(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            2,
            network_id="N_456",
            network_name="Test Network 2",
            metric="current",
        )
        metrics.assert_gauge_value(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            3,
            network_id="N_456",
            network_name="Test Network 2",
            metric="realPower",
        )
        metrics.assert_gauge_value(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            1,
            network_id="N_456",
            network_name="Test Network 2",
            metric="voltage",
        )

        # Verify zero-value metrics are still set
        metrics.assert_gauge_value(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            0,
            network_id="N_123",
            network_name="Test Network 1",
            metric="apparentPower",
        )

    async def test_sensor_alerts_with_empty_response(self, collector, mock_api_builder, metrics):
        """Test sensor alerts with empty response."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")

        # Configure mock API with empty sensor alert response
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAssuranceAlerts", [])
            .with_custom_response("getOrganizationNetworks", [network])
            .with_custom_response("getNetworkSensorAlertsOverviewByMetric", [])
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success - should handle empty response gracefully
        self.assert_collector_success(collector, metrics)

    async def test_sensor_alerts_api_error(self, collector, mock_api_builder, metrics):
        """Test sensor alerts handle API errors gracefully."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")

        # Configure mock API with error for sensor alerts
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAssuranceAlerts", [])
            .with_custom_response("getOrganizationNetworks", [network])
            .with_error("getNetworkSensorAlertsOverviewByMetric", Exception("API Error"))
            .build()
        )
        collector.api = api

        # Run collection - should handle error gracefully
        await self.run_collector(collector)

        # Verify success (errors are handled gracefully)
        self.assert_collector_success(collector, metrics)

    async def test_sensor_alerts_with_no_networks(self, collector, mock_api_builder, metrics):
        """Test sensor alerts when no networks exist."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Configure mock API with no networks
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAssuranceAlerts", [])
            .with_custom_response("getOrganizationNetworks", [])
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success - should handle no networks gracefully
        self.assert_collector_success(collector, metrics)

    async def test_sensor_alerts_malformed_data(self, collector, mock_api_builder, metrics):
        """Test sensor alerts handle malformed data gracefully."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")

        # Create malformed response - missing counts
        sensor_alert_response = [
            {
                "startTs": "2025-07-21T18:00:00Z",
                "endTs": "2025-07-21T18:59:59Z",
                # Missing "counts" key
            }
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAssuranceAlerts", [])
            .with_custom_response("getOrganizationNetworks", [network])
            .with_custom_response("getNetworkSensorAlertsOverviewByMetric", sensor_alert_response)
            .build()
        )
        collector.api = api

        # Run collection - should handle malformed data gracefully
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

    async def test_fan_outs_use_bounded_batching(self, collector, mock_api_builder, metrics):
        """Org alerts and sensor-alert networks must both be.

        Driven through ``process_in_batches_with_errors`` (bounded concurrency),
        never a raw ``asyncio.gather`` fan-out, per issue #248. There is no longer a
        separate health-alert-network fan-out: network health alerts are derived from
        the org-wide getOrganizationAssuranceAlerts response (F-064 / issue #273).
        """
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        networks = [
            NetworkFactory.create(network_id=f"N_{i}", name=f"Network {i}") for i in range(5)
        ]
        sensor_devices = [
            DeviceFactory.create_mt(network_id="N_0", productType="sensor", serial="Q2MT-XXXX-0001")
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_devices(sensor_devices, org_id="123")
            .with_custom_response("getOrganizationAssuranceAlerts", [])
            .with_custom_response("getOrganizationNetworks", networks)
            .with_custom_response("getNetworkSensorAlertsOverviewByMetric", [])
            .build()
        )
        collector.api = api

        # Use a small batch size so bounding is observable, and record every call
        # made to the shared batching helper so we can assert it was actually used
        # (and with what batch size / delay) for each fan-out site.
        collector.settings.api.network_batch_size = 2
        collector.settings.api.batch_delay = 0.0

        calls: list[dict[str, Any]] = []

        async def spying_batches(items, process_func, **kwargs):
            calls.append({"items": list(items), "batch_size": kwargs.get("batch_size")})
            return await process_in_batches_with_errors(items, process_func, **kwargs)

        original = alerts_module.process_in_batches_with_errors
        alerts_module.process_in_batches_with_errors = spying_batches
        try:
            await self.run_collector(collector)
        finally:
            alerts_module.process_in_batches_with_errors = original

        # Verify success and that all networks were still processed / metrics emitted
        self.assert_collector_success(collector, metrics)
        self.assert_api_call_tracked(collector, metrics, "getOrganizationAssuranceAlerts")

        # Deprecated getNetworkHealthAlerts must never be called (F-064).
        api.networks.getNetworkHealthAlerts.assert_not_called()

        # One call for org alerts (1 org), one for sensor-alert networks (1 network
        # with sensors). No third fan-out for health-alert networks anymore.
        assert len(calls) == 2, f"expected 2 batched fan-outs, got {len(calls)}: {calls}"
        for call in calls:
            assert call["batch_size"] == 2

        # Calls are awaited strictly sequentially in _collect_impl, in this order:
        # org alerts, then sensor-alert networks.
        org_call, sensor_call = calls
        assert org_call["items"] == ["123"]
        assert len(sensor_call["items"]) == 1
        assert sensor_call["items"][0]["id"] == "N_0"

    async def test_network_health_alerts_derived_from_assurance_alerts(
        self, collector, mock_api_builder, metrics
    ):
        """Network health alerts must be derived from getOrganizationAssuranceAlerts.

        F-064 / issue #273: the deprecated per-network ``getNetworkHealthAlerts`` call
        is gone; ``meraki_network_health_alerts_total`` is now aggregated (by network,
        categoryType, severity) from the same org-wide assurance alerts response used
        for the other alert metrics, with no per-network API calls at all.
        """
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network_a = NetworkFactory.create(network_id="N_0", name="Network 0")
        network_b = NetworkFactory.create(network_id="N_1", name="Network 1")

        alerts = [
            AlertFactory.create(
                alert_id="alert1",
                alert_type="connectivity",
                categoryType="connectivity",
                severity="warning",
                deviceType="MR",
                network=network_a,
                dismissedAt=None,
                resolvedAt=None,
            ),
            AlertFactory.create(
                alert_id="alert2",
                alert_type="connectivity",
                categoryType="connectivity",
                severity="warning",
                deviceType="MS",
                network=network_a,
                dismissedAt=None,
                resolvedAt=None,
            ),
            AlertFactory.create(
                alert_id="alert3",
                alert_type="crc_errors_error",
                categoryType="device_health",
                severity="critical",
                deviceType="MS",
                network=network_b,
                dismissedAt=None,
                resolvedAt=None,
            ),
            # Resolved -> must not contribute to any count, including health alerts.
            AlertFactory.create(
                alert_id="alert4",
                alert_type="connectivity",
                categoryType="connectivity",
                severity="warning",
                deviceType="MR",
                network=network_b,
                dismissedAt=None,
                resolvedAt="2024-01-01T00:00:00Z",
            ),
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_devices([], org_id="123")
            .with_custom_response("getOrganizationAssuranceAlerts", alerts)
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        self.assert_collector_success(collector, metrics)

        # The deprecated endpoint must never be called.
        api.networks.getNetworkHealthAlerts.assert_not_called()

        metrics.assert_gauge_value(
            AlertMetricName.NETWORK_HEALTH_ALERTS_TOTAL,
            2,
            org_id="123",
            org_name="Test Org",
            network_id="N_0",
            network_name="Network 0",
            category="connectivity",
            severity="warning",
        )
        metrics.assert_gauge_value(
            AlertMetricName.NETWORK_HEALTH_ALERTS_TOTAL,
            1,
            org_id="123",
            org_name="Test Org",
            network_id="N_1",
            network_name="Network 1",
            category="device_health",
            severity="critical",
        )

    async def test_alert_gauges_respect_network_filter(self, collector, metrics):
        """Active/severity/network alert gauges must honor get_allowed_network_ids.

        Previously only the derived network-health-alert metric filtered by the
        allow-list; the active/severity/network gauges emitted series for every
        network, so ``meraki_*_alert*`` series leaked for networks excluded by
        NetworkFilter (bug-bash F-173). All per-network aggregations must now
        skip rows whose network is outside the filter.
        """
        org_id, org_name = "123", "Test Org"
        allowed = NetworkFactory.create(network_id="N_1", name="Allowed Network")
        excluded = NetworkFactory.create(network_id="N_2", name="Excluded Network")

        alerts = [
            AlertFactory.create(
                alert_id="a1",
                alert_type="connectivity",
                categoryType="connectivity",
                severity="critical",
                deviceType="MR",
                network=allowed,
                dismissedAt=None,
                resolvedAt=None,
            ),
            AlertFactory.create(
                alert_id="a2",
                alert_type="performance",
                categoryType="wireless",
                severity="warning",
                deviceType="MS",
                network=excluded,
                dismissedAt=None,
                resolvedAt=None,
            ),
        ]

        collector._process_alerts(alerts, org_id, org_name, allowed_network_ids={"N_1"})

        # Allowed network emits its active + by-network series.
        metrics.assert_gauge_value(
            AlertMetricName.ALERTS_ACTIVE,
            1,
            org_id=org_id,
            org_name=org_name,
            alert_type="connectivity",
            category_type="connectivity",
            severity="critical",
            device_type="MR",
            network_id="N_1",
            network_name="Allowed Network",
        )
        metrics.assert_gauge_value(
            AlertMetricName.ALERTS_TOTAL_BY_NETWORK,
            1,
            org_id=org_id,
            org_name=org_name,
            network_id="N_1",
            network_name="Allowed Network",
        )

        # Excluded network must not emit any series.
        metrics.assert_metric_not_set(
            AlertMetricName.ALERTS_ACTIVE,
            org_id=org_id,
            org_name=org_name,
            alert_type="performance",
            category_type="wireless",
            severity="warning",
            device_type="MS",
            network_id="N_2",
            network_name="Excluded Network",
        )
        metrics.assert_metric_not_set(
            AlertMetricName.ALERTS_TOTAL_BY_NETWORK,
            org_id=org_id,
            org_name=org_name,
            network_id="N_2",
            network_name="Excluded Network",
        )

        # By-severity summary must only count the allowed network's alert.
        metrics.assert_gauge_value(
            AlertMetricName.ALERTS_TOTAL_BY_SEVERITY,
            1,
            org_id=org_id,
            org_name=org_name,
            severity="critical",
        )
        metrics.assert_gauge_value(
            AlertMetricName.ALERTS_TOTAL_BY_SEVERITY,
            0,
            org_id=org_id,
            org_name=org_name,
            severity="warning",
        )

    async def test_fetch_networks_direct_still_applies_network_filter(
        self, mock_api_builder, settings, isolated_registry
    ):
        """Regression guard for the inventory-unavailable fallback.

        ``_fetch_networks_direct`` must remain untouched by the batching change
        and keep manually reapplying the configured NetworkFilter.
        """
        allowed = NetworkFactory.create(network_id="N_allowed", name="Allowed")
        excluded = NetworkFactory.create(network_id="N_excluded", name="Excluded")

        settings.network_filter.include_ids = ["N_allowed"]

        collector = AlertsCollector(
            api=mock_api_builder.build(), settings=settings, registry=isolated_registry
        )
        # No inventory service configured -> forces the direct-fetch fallback path.
        collector.inventory = None

        api = mock_api_builder.with_custom_response(
            "getOrganizationNetworks", [allowed, excluded]
        ).build()
        collector.api = api

        networks = await collector._fetch_networks_direct("123")

        assert networks is not None
        network_ids = {n["id"] for n in networks}
        assert network_ids == {"N_allowed"}

    async def test_alert_gauges_participate_in_expiration(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """All alert gauges must route through _set_metric for expiration tracking.

        F-059: resolved alerts used to stay nonzero forever because
        ``_clear_org_metrics`` was a no-op and every gauge was set via raw
        ``.labels(...).set(...)``, so ``MetricExpirationManager`` never tracked (and
        therefore never reaped) a stale label combination once the underlying alert
        resolved. Every alert gauge must now be tracked with a real ``Gauge``
        reference so the expiration manager can actually remove stale series once
        their TTL elapses.
        """
        from meraki_dashboard_exporter.core.metric_expiration import MetricExpirationManager

        manager = MetricExpirationManager(settings=settings)
        collector = AlertsCollector(
            api=mock_api_builder.build(),
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            expiration_manager=manager,
        )

        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")
        sensor_device = DeviceFactory.create_mt(
            network_id="N_123", productType="sensor", serial="Q2MT-XXXX-0001"
        )

        alert = AlertFactory.create(
            alert_id="alert1",
            alert_type="connectivity",
            categoryType="connectivity",
            severity="critical",
            deviceType="MR",
            network=network,
            dismissedAt=None,
            resolvedAt=None,
        )

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_devices([sensor_device], org_id="123")
            .with_custom_response("getOrganizationAssuranceAlerts", [alert])
            .with_custom_response("getOrganizationNetworks", [network])
            .with_custom_response(
                "getNetworkSensorAlertsOverviewByMetric",
                [{"counts": {"door": 1}}],
            )
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        tracked_metric_names = {key[1] for key in manager._metric_series}
        assert AlertMetricName.ALERTS_ACTIVE.value in tracked_metric_names
        assert AlertMetricName.ALERTS_TOTAL_BY_SEVERITY.value in tracked_metric_names
        assert AlertMetricName.ALERTS_TOTAL_BY_NETWORK.value in tracked_metric_names
        assert AlertMetricName.NETWORK_HEALTH_ALERTS_TOTAL.value in tracked_metric_names
        assert AlertMetricName.SENSOR_ALERTS_TOTAL.value in tracked_metric_names

    async def test_resolved_alert_series_removed_after_ttl(
        self, mock_api_builder, settings, isolated_registry, inventory
    ):
        """A resolved alert's stale series must actually disappear once expired.

        End-to-end regression guard for F-059: run one cycle with an active alert
        (series set to 1), then a second cycle where the alert has resolved (so it
        no longer appears in the API response). Fast-forward past the metric's TTL
        and run ``cleanup_expired_metrics`` — the stale series must be removed from
        the registry, not left stuck at its last value forever.
        """
        from meraki_dashboard_exporter.core.metric_expiration import MetricExpirationManager

        manager = MetricExpirationManager(settings=settings)
        collector = AlertsCollector(
            api=mock_api_builder.build(),
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            expiration_manager=manager,
        )

        org = OrganizationFactory.create(org_id="123", name="Test Org")
        network = NetworkFactory.create(network_id="N_123", name="Test Network")

        active_alert = AlertFactory.create(
            alert_id="alert1",
            alert_type="connectivity",
            categoryType="connectivity",
            severity="critical",
            deviceType="MR",
            network=network,
            dismissedAt=None,
            resolvedAt=None,
        )

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_devices([], org_id="123")
            .with_custom_response("getOrganizationAssuranceAlerts", [active_alert])
            .build()
        )
        collector.api = api

        # Cycle 1: alert is active.
        await self.run_collector(collector)

        metrics = MetricAssertions(isolated_registry)
        metrics.assert_gauge_value(
            AlertMetricName.ALERTS_ACTIVE,
            1,
            org_id="123",
            org_name="Test Org",
            network_id="N_123",
            network_name="Test Network",
            alert_type="connectivity",
            category_type="connectivity",
            severity="critical",
            device_type="MR",
        )

        # Cycle 2: the alert has resolved and no longer appears in the response.
        api.organizations.getOrganizationAssuranceAlerts.return_value = []
        await self.run_collector(collector)

        # The stale series is still present immediately after the resolved cycle
        # (no per-cycle clear -- see the comment in _collect_org_alerts) but is no
        # longer being refreshed, so it is now eligible for TTL-based expiration.
        metrics.assert_gauge_value(
            AlertMetricName.ALERTS_ACTIVE,
            1,
            org_id="123",
            org_name="Test Org",
            network_id="N_123",
            network_name="Test Network",
            alert_type="connectivity",
            category_type="connectivity",
            severity="critical",
            device_type="MR",
        )

        # Fast-forward past the MEDIUM-tier TTL (2x the 300s interval) and reap.
        import time as _time

        original_time = _time.time
        try:
            _time.time = lambda: original_time() + 700
            await manager._cleanup_expired_metrics()
        finally:
            _time.time = original_time

        metrics.assert_metric_not_set(
            AlertMetricName.ALERTS_ACTIVE,
            org_id="123",
            org_name="Test Org",
            network_id="N_123",
            network_name="Test Network",
            alert_type="connectivity",
            category_type="connectivity",
            severity="critical",
            device_type="MR",
        )
