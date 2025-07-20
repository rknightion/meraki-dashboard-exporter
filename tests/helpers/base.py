"""Base test class for collector testing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.constants import UpdateTier

from .metrics import MetricAssertions, MetricSnapshot
from .mock_api import MockAPIBuilder

if TYPE_CHECKING:
    from meraki_dashboard_exporter.core.collector import MetricCollector


class BaseCollectorTest:
    """Base class for collector tests with common fixtures and helpers.

    Subclasses should set:
    - collector_class: The collector class to test
    - update_tier: Expected update tier

    Examples
    --------
    class TestDeviceCollector(BaseCollectorTest):
        collector_class = DeviceCollector
        update_tier = UpdateTier.MEDIUM

        def test_collect_devices(self, collector, mock_api_builder):
            # Test implementation
            pass

    """

    collector_class: type[MetricCollector] | None = None
    update_tier: UpdateTier | None = None

    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set up environment for tests."""
        monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings."""
        return Settings()

    @pytest.fixture
    def isolated_registry(self, monkeypatch: pytest.MonkeyPatch) -> CollectorRegistry:
        """Create an isolated Prometheus registry."""
        registry = CollectorRegistry()
        # Patch the global registry used by collectors
        monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", registry)
        # Also reset the initialization flag and clear class-level metrics
        monkeypatch.setattr(
            "meraki_dashboard_exporter.core.collector.MetricCollector._metrics_initialized", False
        )
        monkeypatch.setattr(
            "meraki_dashboard_exporter.core.collector.MetricCollector._collector_duration", None
        )
        monkeypatch.setattr(
            "meraki_dashboard_exporter.core.collector.MetricCollector._collector_errors", None
        )
        monkeypatch.setattr(
            "meraki_dashboard_exporter.core.collector.MetricCollector._collector_last_success", None
        )
        monkeypatch.setattr(
            "meraki_dashboard_exporter.core.collector.MetricCollector._collector_api_calls", None
        )
        return registry

    @pytest.fixture
    def mock_api_builder(self) -> MockAPIBuilder:
        """Create a mock API builder."""
        return MockAPIBuilder()

    @pytest.fixture
    def mock_api(self, mock_api_builder: MockAPIBuilder) -> MagicMock:
        """Create a default mock API."""
        return mock_api_builder.build()

    @pytest.fixture
    def collector(
        self, mock_api: MagicMock, settings: Settings, isolated_registry: CollectorRegistry
    ) -> MetricCollector:
        """Create the collector instance."""
        if not self.collector_class:
            raise NotImplementedError("Set collector_class in your test class")

        return self.collector_class(api=mock_api, settings=settings, registry=isolated_registry)

    @pytest.fixture
    def metrics(self, isolated_registry: CollectorRegistry) -> MetricAssertions:
        """Create metric assertion helper."""
        return MetricAssertions(isolated_registry)

    @pytest.fixture
    def metric_snapshot(self, isolated_registry: CollectorRegistry) -> MetricSnapshot:
        """Create a metric snapshot."""
        return MetricSnapshot(isolated_registry)

    # Helper methods

    def assert_collector_success(
        self, collector: MetricCollector, metrics: MetricAssertions
    ) -> None:
        """Assert collector ran successfully.

        Parameters
        ----------
        collector : MetricCollector
            The collector instance
        metrics : MetricAssertions
            Metric assertion helper

        """
        # Check collector metrics
        collector_name = collector.__class__.__name__

        # Should have recorded duration
        metrics.assert_histogram_count(
            "meraki_collector_duration_seconds",
            1,
            collector=collector_name,
            tier=(self.update_tier.value if self.update_tier else "medium"),
        )

        # Should have set last success timestamp
        last_success = metrics.get_metric_value(
            "meraki_collector_last_success_timestamp_seconds",
            collector=collector_name,
            tier=(self.update_tier.value if self.update_tier else "medium"),
        )
        assert last_success is not None
        assert last_success > 0

    def assert_collector_error(
        self, collector: MetricCollector, metrics: MetricAssertions, error_type: str = "Exception"
    ) -> None:
        """Assert collector recorded an error.

        Parameters
        ----------
        collector : MetricCollector
            The collector instance
        metrics : MetricAssertions
            Metric assertion helper
        error_type : str
            Expected error type

        """
        collector_name = collector.__class__.__name__

        metrics.assert_counter_incremented(
            "meraki_collector_errors_total",
            collector=collector_name,
            tier=(self.update_tier.value if self.update_tier else "medium"),
            error_type=error_type,
        )

    def assert_api_call_tracked(
        self, collector: MetricCollector, metrics: MetricAssertions, endpoint: str, count: int = 1
    ) -> None:
        """Assert API calls were tracked.

        Parameters
        ----------
        collector : MetricCollector
            The collector instance
        metrics : MetricAssertions
            Metric assertion helper
        endpoint : str
            API endpoint name
        count : int
            Expected call count

        """
        collector_name = collector.__class__.__name__

        metrics.assert_counter_value(
            "meraki_collector_api_calls",
            count,
            collector=collector_name,
            tier=(self.update_tier.value if self.update_tier else "medium"),
            endpoint=endpoint,
        )

    async def run_collector(
        self, collector: MetricCollector, expect_success: bool = True
    ) -> Exception | None:
        """Run collector and optionally check for success.

        Parameters
        ----------
        collector : MetricCollector
            The collector to run
        expect_success : bool
            Whether to expect success

        Returns
        -------
        Exception | None
            Any exception that was raised

        """
        try:
            await collector.collect()
            if not expect_success:
                pytest.fail("Expected collector to fail but it succeeded")
            return None
        except Exception as e:
            if expect_success:
                pytest.fail(f"Collector failed unexpectedly: {e}")
            return e

    def setup_standard_test_data(
        self,
        mock_api_builder: MockAPIBuilder,
        org_count: int = 1,
        network_count: int = 2,
        device_count: int = 4,
    ) -> dict[str, Any]:
        """Set up standard test data on the mock API.

        Parameters
        ----------
        mock_api_builder : MockAPIBuilder
            The API builder to configure
        org_count : int
            Number of organizations
        network_count : int
            Number of networks per org
        device_count : int
            Number of devices per network

        Returns
        -------
        dict[str, Any]
            The test data that was set up

        """
        from .factories import DeviceFactory, NetworkFactory, OrganizationFactory

        # Create organizations
        orgs = OrganizationFactory.create_many(org_count)
        mock_api_builder.with_organizations(orgs)

        # Create networks and devices
        all_networks = []
        all_devices = []

        for org in orgs:
            # Create networks for this org
            networks = NetworkFactory.create_many(network_count, org_id=org["id"])
            all_networks.extend(networks)
            mock_api_builder.with_networks(networks, org_id=org["id"])

            # Create devices for each network
            org_devices = []
            for network in networks:
                devices = DeviceFactory.create_mixed(device_count, network_id=network["id"])
                all_devices.extend(devices)
                org_devices.extend(devices)

            mock_api_builder.with_devices(org_devices, org_id=org["id"])

        return {
            "organizations": orgs,
            "networks": all_networks,
            "devices": all_devices,
        }

    def verify_no_metrics_set(self, metrics: MetricAssertions, metric_names: list[str]) -> None:
        """Verify that none of the given metrics were set.

        Parameters
        ----------
        metrics : MetricAssertions
            Metric assertion helper
        metric_names : list[str]
            List of metric names to check

        """
        for metric_name in metric_names:
            try:
                metric = metrics.get_metric(metric_name)
                # If metric exists, check it has no samples
                samples = [s for s in metric.samples if s.name == metric_name]
                if samples:
                    pytest.fail(
                        f"Metric {metric_name} was set but should not have been. "
                        f"Found {len(samples)} samples."
                    )
            except AssertionError:
                # Metric doesn't exist at all, which is fine
                pass


class AsyncCollectorTestMixin:
    """Mixin for async collector testing patterns.

    Provides additional async test helpers.
    """

    async def collect_with_timeout(self, collector: MetricCollector, timeout: float = 5.0) -> None:
        """Run collector with a timeout.

        Parameters
        ----------
        collector : MetricCollector
            The collector to run
        timeout : float
            Timeout in seconds

        """
        import asyncio

        try:
            await asyncio.wait_for(collector.collect(), timeout=timeout)
        except TimeoutError:
            pytest.fail(f"Collector timed out after {timeout}s")

    async def collect_multiple_times(
        self, collector: MetricCollector, count: int = 3, interval: float = 0.1
    ) -> None:
        """Run collector multiple times.

        Parameters
        ----------
        collector : MetricCollector
            The collector to run
        count : int
            Number of times to run
        interval : float
            Delay between runs

        """
        import asyncio

        for i in range(count):
            await collector.collect()
            if i < count - 1:
                await asyncio.sleep(interval)
