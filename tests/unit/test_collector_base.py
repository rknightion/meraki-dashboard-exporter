"""Tests for the base MetricCollector class."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from meraki_dashboard_exporter.core.collector import MetricCollector
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.constants import UpdateTier


def create_test_collector_class() -> type[MetricCollector]:
    """Create a test collector class dynamically to avoid pytest collection."""

    class TestCollectorImpl(MetricCollector):
        """Test implementation of MetricCollector."""

        update_tier = UpdateTier.MEDIUM

        def _initialize_metrics(self) -> None:
            """Initialize test metrics."""
            self._test_gauge = self._create_gauge(
                "test_gauge",
                "Test gauge metric",
                labelnames=["label1", "label2"],
            )
            self._test_counter = self._create_counter(
                "test_counter",
                "Test counter metric",
                labelnames=["label1"],
            )
            self._test_histogram = self._create_histogram(
                "test_histogram",
                "Test histogram metric",
                labelnames=["label1"],
            )

        async def _collect_impl(self) -> None:
            """Test collection implementation."""
            self._track_api_call("test_api_call")
            self._test_gauge.labels(label1="value1", label2="value2").set(42.0)
            self._test_counter.labels(label1="value1").inc()
            self._test_histogram.labels(label1="value1").observe(1.5)

    return TestCollectorImpl


@pytest.fixture
def mock_api():
    """Create a mock Meraki API client."""
    return MagicMock()


@pytest.fixture
def mock_settings(monkeypatch):
    """Create mock settings."""
    monkeypatch.setenv("MERAKI_API_KEY", "a" * 40)
    return Settings()


@pytest.fixture
def test_collector(mock_api, mock_settings, monkeypatch):
    """Create a test collector instance."""
    # Patch the registry to use an isolated one
    isolated_registry = CollectorRegistry()
    monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)
    test_collector_class = create_test_collector_class()
    return test_collector_class(api=mock_api, settings=mock_settings)


class TestMetricCollector:
    """Test the base MetricCollector functionality."""

    def test_collector_initialization(self, test_collector):
        """Test that collector initializes properly."""
        assert test_collector.api is not None
        assert test_collector.settings is not None
        assert test_collector.update_tier == UpdateTier.MEDIUM

        # Check that metrics were created
        assert hasattr(test_collector, "_test_gauge")
        assert hasattr(test_collector, "_test_counter")
        assert hasattr(test_collector, "_test_histogram")

        # Check internal metrics
        assert hasattr(test_collector, "_collector_duration")
        assert hasattr(test_collector, "_collector_errors")
        assert hasattr(test_collector, "_collector_last_success")
        assert hasattr(test_collector, "_collector_api_calls")

    def test_create_gauge(self, test_collector):
        """Test gauge creation."""
        gauge = test_collector._create_gauge(
            "another_gauge",
            "Another test gauge",
            labelnames=["test"],
        )
        assert isinstance(gauge, Gauge)

    def test_create_counter(self, test_collector):
        """Test counter creation."""
        counter = test_collector._create_counter(
            "another_counter",
            "Another test counter",
            labelnames=["test"],
        )
        assert isinstance(counter, Counter)

    def test_create_histogram(self, test_collector):
        """Test histogram creation."""
        histogram = test_collector._create_histogram(
            "another_histogram",
            "Another test histogram",
            labelnames=["test"],
        )
        assert isinstance(histogram, Histogram)

    @pytest.mark.asyncio
    async def test_collect_success(self, test_collector):
        """Test successful metric collection."""
        # Run collection
        await test_collector.collect()

        # Verify API tracking
        # The metrics are labeled with (collector, tier, api_call)
        found = False
        for key in test_collector._collector_api_calls._metrics:
            if "test_api_call" in str(key):
                found = True
                break
        assert found, (
            f"API call not tracked. Keys: {list(test_collector._collector_api_calls._metrics.keys())}"
        )

    @pytest.mark.asyncio
    async def test_collect_with_error(self, mock_api, mock_settings, monkeypatch):
        """Test collection with error handling."""
        # Use isolated registry
        isolated_registry = CollectorRegistry()
        monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)

        class ErrorCollectorImpl(MetricCollector):
            update_tier = UpdateTier.MEDIUM

            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                raise Exception("Test error")

        collector = ErrorCollectorImpl(api=mock_api, settings=mock_settings)

        # Should raise the exception
        with pytest.raises(Exception, match="Test error"):
            await collector.collect()

        # Error counter should be incremented
        error_found = False
        if collector._collector_errors is not None:
            # Access the internal _metrics dict of the Counter
            metrics = getattr(collector._collector_errors, "_metrics", {})
            for key, metric in metrics.items():
                if "ErrorCollectorImpl" in str(key):
                    error_found = True
                    # Access the metric value
                    value = getattr(metric, "_value", None)
                    if value is not None:
                        assert value.get() > 0
                    break
        assert error_found, (
            f"Error not tracked. Keys: {list(metrics.keys()) if 'metrics' in locals() else []}"
        )

    @pytest.mark.asyncio
    async def test_collect_tracks_duration(self, test_collector):
        """Test that collection tracks duration."""
        # Run collection
        await test_collector.collect()

        # Duration histogram should have been observed
        duration_metrics = test_collector._collector_duration._metrics
        assert len(duration_metrics) > 0

        # Get the metric for our collector
        for key, metric in duration_metrics.items():
            if ("collector", "TestCollectorImpl") in key:
                assert metric._count.get() == 1
                assert metric._sum.get() > 0  # Should have recorded some duration

    @pytest.mark.asyncio
    async def test_collect_updates_last_success(self, test_collector):
        """Test that successful collection updates last success timestamp."""
        import time

        # Get timestamp before collection
        before_time = time.time()

        # Run collection
        await test_collector.collect()

        # Get last success timestamp
        last_success_metrics = test_collector._collector_last_success._metrics
        for key, metric in last_success_metrics.items():
            if ("collector", "TestCollectorImpl") in key:
                timestamp = metric._value.get()
                assert timestamp >= before_time
                assert timestamp <= time.time()

    def test_track_api_call(self, test_collector):
        """Test API call tracking."""
        # Track multiple API calls
        test_collector._track_api_call("getOrganizations")
        test_collector._track_api_call("getOrganizations")
        test_collector._track_api_call("getNetworks")

        # Check counters
        api_metrics = test_collector._collector_api_calls._metrics

        # Find our metrics
        org_count = 0
        net_count = 0
        for key, metric in api_metrics.items():
            if "getOrganizations" in str(key):
                org_count = metric._value.get()
            elif "getNetworks" in str(key):
                net_count = metric._value.get()

        assert org_count == 2, (
            f"Expected 2 getOrganizations calls, got {org_count}. Keys: {list(api_metrics.keys())}"
        )
        assert net_count == 1, f"Expected 1 getNetworks call, got {net_count}"

    @pytest.mark.asyncio
    async def test_concurrent_collections(self, test_collector):
        """Test that concurrent collections work properly."""
        import asyncio

        # Run multiple collections concurrently
        tasks = [test_collector.collect() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Check that all collections completed
        duration_metrics = test_collector._collector_duration._metrics
        for key, metric in duration_metrics.items():
            if ("collector", "TestCollectorImpl") in key:
                assert metric._count.get() == 5  # All 5 collections should have completed

    def test_collector_name(self, test_collector):
        """Test that collector name is properly set."""
        # Internal metrics should use the collector class name
        found = False
        for key in test_collector._collector_duration._metrics.keys():
            if "TestCollectorImpl" in str(key):
                found = True
                break
        assert found, (
            f"Collector name not found in metrics. Keys: {list(test_collector._collector_duration._metrics.keys())}"
        )
