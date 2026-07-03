"""Tests for MTSensorAlertsCollector - network-wide MT sensor alerting (#268)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.mt_alerts import MTSensorAlertsCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.error_handling import NothingCollectedError
from meraki_dashboard_exporter.core.org_health import OrgHealthTracker
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import NetworkFactory, OrganizationFactory

METRIC_NAME = "meraki_mt_alerting_sensors_count"


def _backed_off_tracker(org_id: str) -> OrgHealthTracker:
    """Build a tracker with ``org_id`` driven into backoff (should_collect False)."""
    tracker = OrgHealthTracker()
    for _ in range(tracker.max_consecutive_failures):
        tracker.record_failure(org_id, "Backed Org")
    assert tracker.should_collect(org_id) is False
    return tracker


class TestMTSensorAlertsCollectorOrgHealthGating(BaseCollectorTest):
    """F-169: MTSensorAlertsCollector honours the shared OrgHealthTracker per-org gate.

    #509: the backoff pre-filter moved from ``_collect_org_sensor_alerts`` into
    ``_collect_impl`` (so an all-orgs-in-backoff cycle is visible to the
    coordinator's failure accounting). ``_collect_org_sensor_alerts`` itself no
    longer re-checks the tracker, so gating is now exercised end-to-end via
    ``_collect_impl``.
    """

    collector_class = MTSensorAlertsCollector
    update_tier = UpdateTier.MEDIUM

    async def test_backed_off_org_is_skipped(
        self, mock_api, settings, isolated_registry, inventory
    ):
        """A backed-off org is skipped before fetching networks; a healthy org is not."""
        tracker = _backed_off_tracker("BACKED")
        collector = MTSensorAlertsCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            org_health_tracker=tracker,
        )
        collector.inventory.get_organizations = AsyncMock(
            return_value=[
                {"id": "BACKED", "name": "Backed Org"},
                {"id": "HEALTHY", "name": "Healthy Org"},
            ]
        )
        seen: list[str] = []

        async def _spy(org_id: str) -> list:
            seen.append(org_id)
            return []

        collector.inventory.get_networks = _spy  # type: ignore[method-assign]

        await collector._collect_impl()
        assert seen == ["HEALTHY"]  # backed-off org never reaches the network fetch

    async def test_none_tracker_collects_all(self, collector):
        """With no tracker wired in, every org is collected (backward compatible)."""
        assert collector.org_health_tracker is None
        seen: list[str] = []

        async def _spy(org_id: str) -> list:
            seen.append(org_id)
            return []

        collector.inventory.get_networks = _spy  # type: ignore[method-assign]

        await collector._collect_org_sensor_alerts("ANY", "Any Org")
        assert seen == ["ANY"]


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
            network_id="N_1",
            metric="temperature",
        ).set(3)

        metrics.assert_gauge_value(
            METRIC_NAME,
            3,
            org_id="123456",
            network_id="N_1",
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
            network_id="N_1",
            metric="temperature",
        )
        assertions.assert_gauge_value(
            METRIC_NAME,
            1,
            org_id="123456",
            network_id="N_1",
            metric="humidity",
        )
        assertions.assert_gauge_value(
            METRIC_NAME,
            3,
            org_id="123456",
            network_id="N_1",
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
            network_id="N_1",
            metric="temperature",
        )

    async def test_collect_impl_requires_inventory(self, settings, isolated_registry, mock_api):
        """Without inventory configured, _collect_impl raises (#509: no swallow)."""
        collector = MTSensorAlertsCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=None,
        )

        # The @with_error_handling(continue_on_error=True) decorator was removed
        # from _collect_impl (#509), so this programming-error RuntimeError now
        # propagates instead of being swallowed.
        with pytest.raises(RuntimeError):
            await collector._collect_impl()

    async def test_collect_impl_no_organizations(self, collector) -> None:
        """No organizations -> returns cleanly without error."""
        collector.inventory.get_organizations = AsyncMock(return_value=[])
        await collector._collect_impl()


class TestMTSensorAlertsCollectorNothingCollected(BaseCollectorTest):
    """#509: total-failure and all-in-backoff cycles must raise, not swallow.

    ``MTSensorAlertsCollector`` was a validated scope addition to #509: its
    ``_collect_impl`` decorated ``@with_error_handling(continue_on_error=True)``
    would otherwise keep the MEDIUM tier marked complete under a revoked API key.
    """

    collector_class = MTSensorAlertsCollector
    update_tier = UpdateTier.MEDIUM

    async def test_org_fetch_failure_raises(self, collector) -> None:
        """A failure fetching networks for the only org must propagate.

        The coordinator uses ``ManagedTaskGroup``, so the worker's underlying
        exception is swallowed by the group and the coordinator raises its own
        ``NothingCollectedError`` once it observes zero successes -- either way,
        the collection must not return cleanly.
        """
        collector.inventory.get_organizations = AsyncMock(
            return_value=[{"id": "123456", "name": "Test Org"}]
        )
        collector.inventory.get_networks = AsyncMock(side_effect=Exception("Connection error"))

        with pytest.raises(NothingCollectedError):
            await collector._collect_impl()

    async def test_all_orgs_failed_raises_nothing_collected(self, collector) -> None:
        """A single org whose network fetch errors -> NothingCollectedError."""
        collector.inventory.get_organizations = AsyncMock(
            return_value=[{"id": "123456", "name": "Test Org"}]
        )
        collector.inventory.get_networks = AsyncMock(side_effect=Exception("Connection error"))

        with pytest.raises(NothingCollectedError) as exc_info:
            await collector._collect_impl()
        assert exc_info.value.failed == 1
        assert exc_info.value.skipped_backoff == 0

    async def test_partial_org_failure_does_not_raise(self, collector, metrics) -> None:
        """One of two orgs failing must not raise -- the healthy org still succeeds."""
        collector.inventory.get_organizations = AsyncMock(
            return_value=[
                {"id": "BAD", "name": "Bad Org"},
                {"id": "GOOD", "name": "Good Org"},
            ]
        )

        good_network = NetworkFactory.create(
            network_id="N_good", org_id="GOOD", product_types=["sensor"]
        )

        async def _get_networks(org_id: str) -> list:
            if org_id == "BAD":
                raise Exception("Connection error")
            return [good_network]

        collector.inventory.get_networks = _get_networks  # type: ignore[method-assign]
        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            return_value={"supportedMetrics": ["temperature"], "counts": {"temperature": 1}}
        )

        await collector._collect_impl()

        metrics.assert_gauge_value(
            METRIC_NAME,
            1,
            org_id="GOOD",
            network_id="N_good",
            metric="temperature",
        )

    async def test_all_orgs_in_backoff_raises(self, collector) -> None:
        """Every org in backoff must raise NothingCollectedError with skipped_backoff set."""
        collector.inventory.get_organizations = AsyncMock(
            return_value=[{"id": "123456", "name": "Test Org"}]
        )
        collector.org_health_tracker = _backed_off_tracker("123456")

        with pytest.raises(NothingCollectedError) as exc_info:
            await collector._collect_impl()
        assert exc_info.value.failed == 0
        assert exc_info.value.skipped_backoff == 1

    async def test_empty_org_list_is_success(self, collector) -> None:
        """An empty org list is a legitimate no-op, not a failure."""
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


PROFILES_METRIC_NAME = "meraki_mt_alert_profiles"
RELATED_DEVICE_METRIC_NAME = "meraki_mt_related_device_info"


class TestMTAlertProfiles(BaseCollectorTest):
    """#302: configured sensor alert profile count per network."""

    collector_class = MTSensorAlertsCollector
    update_tier = UpdateTier.MEDIUM

    async def test_collect_network_alert_profiles_emits_count(self, collector, metrics) -> None:
        """A non-empty profiles list emits its length."""
        collector.api.sensor.getNetworkSensorAlertsProfiles = MagicMock(
            return_value=[{"id": "1"}, {"id": "2"}]
        )

        network = {"id": "N_1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_alert_profiles(network)

        collector.api.sensor.getNetworkSensorAlertsProfiles.assert_called_once_with("N_1")
        metrics.assert_gauge_value(
            PROFILES_METRIC_NAME,
            2,
            org_id="123456",
            network_id="N_1",
        )

    async def test_collect_network_alert_profiles_empty_list_emits_zero(
        self, collector, metrics
    ) -> None:
        """An empty list ([]) is the documented normal case and IS emitted as 0."""
        collector.api.sensor.getNetworkSensorAlertsProfiles = MagicMock(return_value=[])

        network = {"id": "N_1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_alert_profiles(network)

        metrics.assert_gauge_value(
            PROFILES_METRIC_NAME,
            0,
            org_id="123456",
            network_id="N_1",
        )

    async def test_collect_network_alert_profiles_error_skips_emission(
        self, collector, metrics
    ) -> None:
        """A fetch error (not an empty list) must skip emission entirely."""
        collector.api.sensor.getNetworkSensorAlertsProfiles = MagicMock(
            side_effect=Exception("boom")
        )

        network = {"id": "N_1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_alert_profiles(network)

        metrics.assert_metric_not_set(PROFILES_METRIC_NAME, network_id="N_1")

    async def test_collect_impl_end_to_end_with_profiles(
        self, collector, mock_api_builder, metrics
    ) -> None:
        """Full cycle emits both the alerting-count and the alert-profiles metrics."""
        org = OrganizationFactory.create(org_id="123456", name="Test Org")
        network = NetworkFactory.create(
            network_id="N_1", name="Net 1", org_id="123456", product_types=["sensor"]
        )

        mock_api_builder.with_organizations([org]).with_networks([network], org_id="123456")
        collector.api = mock_api_builder.build()
        collector.inventory.api = collector.api
        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            return_value={"supportedMetrics": ["temperature"], "counts": {"temperature": 1}}
        )
        collector.api.sensor.getNetworkSensorAlertsProfiles = MagicMock(return_value=[{"id": "1"}])

        await self.run_collector(collector)

        metrics.assert_gauge_value(
            PROFILES_METRIC_NAME,
            1,
            org_id="123456",
            network_id="N_1",
        )


class TestMTRelatedDeviceInfo(BaseCollectorTest):
    """#308: MT sensor <-> related-device relationship join carrier."""

    collector_class = MTSensorAlertsCollector
    update_tier = UpdateTier.MEDIUM

    async def test_collect_network_relationships_emits_one_series_per_link(
        self, collector, metrics
    ) -> None:
        """One series per sensor->related-device link."""
        collector.api.sensor.getNetworkSensorRelationships = MagicMock(
            return_value=[
                {
                    "device": {"serial": "Q2XX-SENSOR"},
                    "relationships": {
                        "livestream": {
                            "relatedDevices": [
                                {"serial": "Q2YY-CAMERA", "productType": "camera"},
                            ]
                        }
                    },
                }
            ]
        )

        network = {"id": "N_1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_relationships(network)

        collector.api.sensor.getNetworkSensorRelationships.assert_called_once_with("N_1")
        metrics.assert_gauge_value(
            RELATED_DEVICE_METRIC_NAME,
            1,
            org_id="123456",
            network_id="N_1",
            sensor_serial="Q2XX-SENSOR",
            related_serial="Q2YY-CAMERA",
            product_type="camera",
        )

    async def test_collect_network_relationships_multiple_related_devices(
        self, collector, metrics
    ) -> None:
        """Multiple related devices under one sensor each get their own series."""
        collector.api.sensor.getNetworkSensorRelationships = MagicMock(
            return_value=[
                {
                    "device": {"serial": "Q2XX-SENSOR"},
                    "relationships": {
                        "livestream": {
                            "relatedDevices": [
                                {"serial": "Q2YY-CAM1", "productType": "camera"},
                                {"serial": "Q2ZZ-CAM2", "productType": "camera"},
                            ]
                        }
                    },
                }
            ]
        )

        network = {"id": "N_1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_relationships(network)

        metrics.assert_gauge_value(
            RELATED_DEVICE_METRIC_NAME,
            1,
            org_id="123456",
            network_id="N_1",
            sensor_serial="Q2XX-SENSOR",
            related_serial="Q2YY-CAM1",
            product_type="camera",
        )
        metrics.assert_gauge_value(
            RELATED_DEVICE_METRIC_NAME,
            1,
            org_id="123456",
            network_id="N_1",
            sensor_serial="Q2XX-SENSOR",
            related_serial="Q2ZZ-CAM2",
            product_type="camera",
        )

    async def test_collect_network_relationships_no_livestream_is_noop(
        self, collector, metrics
    ) -> None:
        """A sensor entry with no relationships.livestream emits nothing."""
        collector.api.sensor.getNetworkSensorRelationships = MagicMock(
            return_value=[{"device": {"serial": "Q2XX-SENSOR"}, "relationships": {}}]
        )

        network = {"id": "N_1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_relationships(network)

        metrics.assert_metric_not_set(RELATED_DEVICE_METRIC_NAME, network_id="N_1")

    async def test_collect_network_relationships_missing_device_serial_skipped(
        self, collector, metrics
    ) -> None:
        """An entry with no device.serial is skipped entirely."""
        collector.api.sensor.getNetworkSensorRelationships = MagicMock(
            return_value=[
                {
                    "device": {},
                    "relationships": {
                        "livestream": {
                            "relatedDevices": [{"serial": "Q2YY-CAM1", "productType": "camera"}]
                        }
                    },
                }
            ]
        )

        network = {"id": "N_1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_relationships(network)

        metrics.assert_metric_not_set(RELATED_DEVICE_METRIC_NAME, network_id="N_1")

    async def test_collect_network_relationships_error_skips_emission(
        self, collector, metrics
    ) -> None:
        """A fetch error skips emission entirely."""
        collector.api.sensor.getNetworkSensorRelationships = MagicMock(
            side_effect=Exception("boom")
        )

        network = {"id": "N_1", "orgId": "123456", "orgName": "Test Org"}
        await collector._collect_network_relationships(network)

        metrics.assert_metric_not_set(RELATED_DEVICE_METRIC_NAME, network_id="N_1")


class TestMTSensorAlertsCollectorGroupIndependence(BaseCollectorTest):
    """#302/#308: each new group's due-ness gates independently of MT_SENSOR_ALERTS."""

    collector_class = MTSensorAlertsCollector
    update_tier = UpdateTier.MEDIUM

    async def test_collect_org_sensor_alerts_defaults_only_run_alerts(self, collector) -> None:
        """The legacy 2-arg call shape (org_id, org_name) runs only the alerting-count fetch.

        Not the two new Phase 4 fetches - this keeps direct callers/tests that
        predate #618 backward compatible.
        """
        sensor_network = NetworkFactory.create(
            network_id="N_1", org_id="123456", product_types=["sensor"]
        )
        collector.inventory.get_networks = AsyncMock(return_value=[sensor_network])
        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            return_value={"supportedMetrics": [], "counts": {}}
        )
        collector.api.sensor.getNetworkSensorAlertsProfiles = MagicMock(return_value=[])
        collector.api.sensor.getNetworkSensorRelationships = MagicMock(return_value=[])

        await collector._collect_org_sensor_alerts("123456", "Test Org")

        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric.assert_called_once()
        collector.api.sensor.getNetworkSensorAlertsProfiles.assert_not_called()
        collector.api.sensor.getNetworkSensorRelationships.assert_not_called()

    async def test_collect_org_sensor_alerts_explicit_dues_gate_each_fetch(self, collector) -> None:
        """Each of the three fetches only runs when its own due flag is True."""
        sensor_network = NetworkFactory.create(
            network_id="N_1", org_id="123456", product_types=["sensor"]
        )
        collector.inventory.get_networks = AsyncMock(return_value=[sensor_network])
        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            return_value={"supportedMetrics": [], "counts": {}}
        )
        collector.api.sensor.getNetworkSensorAlertsProfiles = MagicMock(return_value=[])
        collector.api.sensor.getNetworkSensorRelationships = MagicMock(return_value=[])

        await collector._collect_org_sensor_alerts(
            "123456",
            "Test Org",
            alerts_due=False,
            profiles_due=True,
            relationships_due=False,
        )

        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric.assert_not_called()
        collector.api.sensor.getNetworkSensorAlertsProfiles.assert_called_once()
        collector.api.sensor.getNetworkSensorRelationships.assert_not_called()

    async def test_collect_impl_marks_only_due_groups(self, collector) -> None:
        """_collect_impl only advances the scheduler clock for groups it computed as due."""
        org = OrganizationFactory.create(org_id="123456", name="Test Org")
        sensor_network = NetworkFactory.create(
            network_id="N_1", org_id="123456", product_types=["sensor"]
        )
        collector.inventory.get_organizations = AsyncMock(return_value=[org])
        collector.inventory.get_networks = AsyncMock(return_value=[sensor_network])
        collector.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric = MagicMock(
            return_value={"supportedMetrics": [], "counts": {}}
        )

        collector._should_run_group = MagicMock(  # type: ignore[method-assign]
            side_effect=lambda group: str(group) == "mt_sensor_alerts"
        )
        collector._mark_group_ran = MagicMock()  # type: ignore[method-assign]

        await collector._collect_impl()

        collector._mark_group_ran.assert_called_once_with(EndpointGroupName.MT_SENSOR_ALERTS)
