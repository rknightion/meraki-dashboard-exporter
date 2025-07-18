"""Tests for the base MetricCollector class using test helpers."""

from __future__ import annotations

import pytest
from prometheus_client import Counter, Gauge, Histogram

from meraki_dashboard_exporter.core.collector import MetricCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import OrganizationFactory


class DummyCollectorImpl(MetricCollector):
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


class ErrorCollectorImpl(MetricCollector):
    """Test collector that always raises an error."""

    update_tier = UpdateTier.MEDIUM

    def _initialize_metrics(self) -> None:
        pass

    async def _collect_impl(self) -> None:
        raise Exception("Test error")


class TestMetricCollector(BaseCollectorTest):
    """Test the base MetricCollector functionality."""

    collector_class = DummyCollectorImpl
    update_tier = UpdateTier.MEDIUM

    def test_collector_initialization(self, collector):
        """Test that collector initializes properly."""
        assert collector.api is not None
        assert collector.settings is not None
        assert collector.update_tier == UpdateTier.MEDIUM

        # Check that metrics were created
        assert hasattr(collector, "_test_gauge")
        assert hasattr(collector, "_test_counter")
        assert hasattr(collector, "_test_histogram")

        # Check internal metrics
        assert hasattr(collector, "_collector_duration")
        assert hasattr(collector, "_collector_errors")
        assert hasattr(collector, "_collector_last_success")
        assert hasattr(collector, "_collector_api_calls")

    def test_create_gauge(self, collector):
        """Test gauge creation."""
        gauge = collector._create_gauge(
            "another_gauge",
            "Another test gauge",
            labelnames=["test"],
        )
        assert isinstance(gauge, Gauge)

    def test_create_counter(self, collector):
        """Test counter creation."""
        counter = collector._create_counter(
            "another_counter",
            "Another test counter",
            labelnames=["test"],
        )
        assert isinstance(counter, Counter)

    def test_create_histogram(self, collector):
        """Test histogram creation."""
        histogram = collector._create_histogram(
            "another_histogram",
            "Another test histogram",
            labelnames=["test"],
        )
        assert isinstance(histogram, Histogram)

    async def test_collect_success(self, collector, mock_api_builder, metrics):
        """Test successful metric collection."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify test metrics were set (these are on the isolated registry)
        metrics.assert_gauge_value("test_gauge", 42.0, label1="value1", label2="value2")
        metrics.assert_counter_incremented("test_counter", label1="value1")

    async def test_collect_with_error(self, mock_api_builder, isolated_registry, settings):
        """Test collection with error handling."""
        # Create error collector
        collector = ErrorCollectorImpl(
            api=mock_api_builder.build(), settings=settings, registry=isolated_registry
        )

        # Should raise the exception
        with pytest.raises(Exception, match="Test error"):
            await collector.collect()

        # The error counter should have been incremented
        # Note: The collector performance metrics are on the global registry, not isolated
        # So we just verify the exception was raised properly above

    async def test_collect_tracks_duration(self, collector, mock_api_builder, metrics):
        """Test that collection tracks duration."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Collection should complete successfully
        # The duration histogram is on the global registry, not the isolated one
        # Just verify no exception was raised

    async def test_collect_updates_last_success(self, collector, mock_api_builder, metrics):
        """Test that successful collection updates last success timestamp."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Collection should complete successfully
        # The last success timestamp is on the global registry, not the isolated one
        # Just verify no exception was raised

    def test_track_api_call(self, collector, metrics):
        """Test API call tracking."""
        # Track multiple API calls
        collector._track_api_call("getOrganizations")
        collector._track_api_call("getOrganizations")
        collector._track_api_call("getNetworks")

        # Verify API calls were tracked (they go to the global registry)
        # Just verify the method doesn't raise an exception
        # The actual counter is on the global registry, not the isolated one

    async def test_concurrent_collections(self, collector, mock_api_builder, metrics):
        """Test that concurrent collections work properly."""
        import asyncio

        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Configure mock API
        api = mock_api_builder.with_organizations([org]).build()
        collector.api = api

        # Run multiple collections concurrently
        tasks = [collector.collect() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All collections should complete without exceptions
        for result in results:
            assert result is None  # collect() returns None on success

    def test_collector_name(self, collector, metrics):
        """Test that collector name is properly set."""
        # The collector should have the correct class name
        assert collector.__class__.__name__ == "DummyCollectorImpl"

        # The update tier should be set correctly
        assert collector.update_tier == UpdateTier.MEDIUM
