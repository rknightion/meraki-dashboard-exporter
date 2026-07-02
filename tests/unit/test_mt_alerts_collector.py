"""Tests for MTSensorAlertsCollector - network-wide MT sensor alerting (#268)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from meraki_dashboard_exporter.collectors.mt_alerts import MTSensorAlertsCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import NetworkFactory, OrganizationFactory

METRIC_NAME = "meraki_mt_alerting_sensors_count"


class TestMTSensorAlertsCollector(BaseCollectorTest):
    """Test MTSensorAlertsCollector functionality."""

    collector_class = MTSensorAlertsCollector
    update_tier = UpdateTier.MEDIUM

    def test_collector_is_medium_tier(self) -> None:
        """The collector is decorated @register_collector(UpdateTier.MEDIUM)."""
        assert MTSensorAlertsCollector.update_tier == UpdateTier.MEDIUM

    def test_gauge_registered_with_full_label_set(self, collector, metrics) -> None:
        """The gauge exists under the frozen metric name with the documented label set."""
        collector._alerting_sensors_count.labels(
            org_id="123456",
            org_name="Test Org",
            network_id="N_1",
            network_name="Net 1",
            metric="temperature",
        ).set(3)

        metrics.assert_gauge_value(
            METRIC_NAME,
            3,
            org_id="123456",
            org_name="Test Org",
            network_id="N_1",
            network_name="Net 1",
            metric="temperature",
        )

    # --- _normalize_count ---

    def test_normalize_count_plain_int(self, collector) -> None:
        """A plain int count passes through unchanged."""
        assert collector._normalize_count(5) == 5

    def test_normalize_count_nested_dict_sums_int_leaves(self, collector) -> None:
        """Nested dicts (e.g. noise.ambient) are summed across integer leaf values."""
        assert collector._normalize_count({"ambient": 3}) == 3

    def test_normalize_count_nested_dict_multiple_leaves(self, collector) -> None:
        """Multiple integer leaves in a nested dict are summed together."""
        assert collector._normalize_count({"ambient": 2, "other": 1}) == 3

    def test_normalize_count_empty_dict_is_none(self, collector) -> None:
        """An empty nested dict has no leaves to sum, so it normalizes to None."""
        assert collector._normalize_count({}) is None

    def test_normalize_count_non_numeric_is_none(self, collector) -> None:
        """Non-numeric/missing values normalize to None instead of raising."""
        assert collector._normalize_count("not-a-number") is None
        assert collector._normalize_count(None) is None

    # --- _collect_network_alerts ---

    async def test_collect_network_alerts_emits_counts_per_metric(self, collector) -> None:
        """Each key in `counts` becomes its own labelled sample, incl. nested noise.ambient."""
        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            return_value={
                "supportedMetrics": ["temperature", "humidity", "noise"],
                "counts": {
                    "temperature": 2,
                    "humidity": 1,
                    "noise": {"ambient": 3},
                },
            }
        )

        network = {"id": "N_1", "name": "Net 1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_alerts(network)

        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric.assert_called_once_with(
            "N_1"
        )

        from tests.helpers.metrics import MetricAssertions

        assertions = MetricAssertions(collector.registry)
        assertions.assert_gauge_value(
            METRIC_NAME,
            2,
            org_id="123456",
            org_name="Test Org",
            network_id="N_1",
            network_name="Net 1",
            metric="temperature",
        )
        assertions.assert_gauge_value(
            METRIC_NAME,
            1,
            org_id="123456",
            org_name="Test Org",
            network_id="N_1",
            network_name="Net 1",
            metric="humidity",
        )
        assertions.assert_gauge_value(
            METRIC_NAME,
            3,
            org_id="123456",
            org_name="Test Org",
            network_id="N_1",
            network_name="Net 1",
            metric="noise",
        )

    async def test_collect_network_alerts_empty_counts(self, collector, metrics) -> None:
        """An overview with empty counts sets no metrics."""
        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            return_value={"supportedMetrics": [], "counts": {}}
        )

        network = {"id": "N_1", "name": "Net 1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_alerts(network)

        metrics.assert_metric_not_set(METRIC_NAME, network_id="N_1")

    async def test_collect_network_alerts_handles_none_overview(self, collector, metrics) -> None:
        """A None overview (e.g. from an error swallowed by with_error_handling) is a no-op."""
        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            side_effect=Exception("boom")
        )

        network = {"id": "N_1", "name": "Net 1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_alerts(network)

        metrics.assert_metric_not_set(METRIC_NAME, network_id="N_1")

    # --- _collect_org_sensor_alerts: sensor-network filtering ---

    async def test_collect_org_sensor_alerts_filters_to_sensor_networks(self, collector) -> None:
        """Only networks with 'sensor' in productTypes are queried."""
        sensor_network = NetworkFactory.create(
            network_id="N_sensor", org_id="123456", product_types=["sensor"]
        )
        wireless_network = NetworkFactory.create(
            network_id="N_wireless", org_id="123456", product_types=["wireless"]
        )
        collector.inventory.get_networks = AsyncMock(
            return_value=[sensor_network, wireless_network]
        )

        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            return_value={"supportedMetrics": ["temperature"], "counts": {"temperature": 1}}
        )

        await collector._collect_org_sensor_alerts("123456", "Test Org")

        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric.assert_called_once_with(
            "N_sensor"
        )

    async def test_collect_org_sensor_alerts_no_sensor_networks_skips_api_call(
        self, collector
    ) -> None:
        """No sensor-capable networks -> the per-network endpoint is never called."""
        wireless_network = NetworkFactory.create(
            network_id="N_wireless", org_id="123456", product_types=["wireless"]
        )
        collector.inventory.get_networks = AsyncMock(return_value=[wireless_network])
        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            return_value={"supportedMetrics": [], "counts": {}}
        )

        await collector._collect_org_sensor_alerts("123456", "Test Org")

        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric.assert_not_called()

    # --- _collect_impl: end to end ---

    async def test_collect_impl_end_to_end(self, collector, mock_api_builder, metrics) -> None:
        """Full collection cycle: org -> sensor network -> alerting counts."""
        org = OrganizationFactory.create(org_id="123456", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_1", name="Net 1", org_id="123456", product_types=["sensor"]
        )

        mock_api_builder.with_organizations([org]).with_networks([network], org_id="123456")
        collector.api = mock_api_builder.build()
        collector.inventory.api = collector.api
        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            return_value={"supportedMetrics": ["temperature"], "counts": {"temperature": 4}}
        )

        await self.run_collector(collector)

        metrics.assert_gauge_value(
            METRIC_NAME,
            4,
            org_id="123456",
            org_name="Test Org",
            network_id="N_1",
            network_name="Net 1",
            metric="temperature",
        )

    async def test_collect_impl_requires_inventory(self, settings, isolated_registry, mock_api):
        """Without inventory configured, _collect_impl logs and does not raise."""
        collector = MTSensorAlertsCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=None,
        )

        # Should be swallowed by @with_error_handling(continue_on_error=True), not raised.
        await collector._collect_impl()

    async def test_collect_impl_no_organizations(self, collector) -> None:
        """No organizations -> returns cleanly without error."""
        collector.inventory.get_organizations = AsyncMock(return_value=[])
        await collector._collect_impl()


def test_sensor_alerts_overview_validates_via_domain_model() -> None:
    """F-023: the sensor alerts overview is parsed via a typed Pydantic domain model."""
    from meraki_dashboard_exporter.core.domain_models import SensorAlertsOverviewByMetric

    overview = SensorAlertsOverviewByMetric.model_validate({
        "supportedMetrics": ["temperature", "humidity", "noise"],
        "counts": {"temperature": 2, "humidity": 1, "noise": {"ambient": 3}},
    })

    assert overview.supportedMetrics == ["temperature", "humidity", "noise"]
    assert overview.counts == {"temperature": 2, "humidity": 1, "noise": {"ambient": 3}}
