"""Tests for the AlertsCollector using test helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from meraki_dashboard_exporter.collectors.alerts import AlertsCollector
from meraki_dashboard_exporter.core.constants import AlertMetricName, UpdateTier
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import AlertFactory, NetworkFactory, OrganizationFactory
from tests.helpers.metrics import MetricAssertions


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
            mock_api_builder.with_organizations([org])
            .with_custom_response("getOrganizationAssuranceAlerts", [])
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

        # The API call tracking expects two calls - one for getOrganization and one for getOrganizationAssuranceAlerts
        # But the mock doesn't call getOrganizations, it calls getOrganization
        self.assert_api_call_tracked(collector, metrics, "getOrganization")
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
            mock_api_builder.with_organizations([org])
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
            mock_api_builder.with_organizations([org])
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
            mock_api_builder.with_organizations([org])
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
            mock_api_builder.with_organizations([org])
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
            mock_api_builder.with_organizations([org])
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
            mock_api_builder.with_organizations([org])
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
            mock_api_builder.with_organizations([org])
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
            mock_api_builder.with_organizations([org])
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
            mock_api_builder.with_organizations([org])
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
