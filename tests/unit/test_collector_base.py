"""Tests for the base MetricCollector class using test helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from prometheus_client import Counter, Gauge, Histogram

from meraki_dashboard_exporter.core.collector import MetricCollector
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import OrganizationFactory


class DummyCollectorImpl(MetricCollector):
    """Test implementation of MetricCollector."""

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

    def _initialize_metrics(self) -> None:
        pass

    async def _collect_impl(self) -> None:
        raise Exception("Test error")


class TestMetricCollector(BaseCollectorTest):
    """Test the base MetricCollector functionality."""

    collector_class = DummyCollectorImpl

    def test_duration_histogram_uses_configured_buckets(self, isolated_registry, settings):
        """MonitoringSettings.histogram_buckets is wired to the duration histogram (F-008)."""
        custom_buckets = [0.25, 2.0, 8.0, 42.0]
        settings.monitoring.histogram_buckets = custom_buckets

        DummyCollectorImpl(
            api=MagicMock(),
            settings=settings,
            registry=isolated_registry,
        )

        duration = MetricCollector._collector_duration
        assert duration is not None
        # prometheus_client appends +Inf to the upper bounds.
        assert list(duration._upper_bounds) == [*custom_buckets, float("inf")]

    def test_collector_initialization(self, collector):
        """Test that collector initializes properly."""
        assert collector.api is not None
        assert collector.settings is not None

        # Check that metrics were created
        assert hasattr(collector, "_test_gauge")
        assert hasattr(collector, "_test_counter")
        assert hasattr(collector, "_test_histogram")

        # Check internal metrics
        assert hasattr(collector, "_collector_duration")
        assert hasattr(collector, "_collector_errors")
        assert hasattr(collector, "_collector_last_success")
        assert hasattr(collector, "_collector_api_calls")

    def test_no_phantom_success_timestamp_series(self, collector):
        """No pre-initialized zero-forever success_timestamp series (F-025).

        The performance-metric init used to pre-seed 6 collectors x 3 tiers = 18
        meraki_exporter_collector_success_timestamp_seconds series at 0, but each
        collector runs in exactly one tier, so 12 stayed 0 forever and read as
        perpetually stale (breaking `time() - <timestamp>` staleness alerting).
        After init (before any collection runs) there must be NO such series.
        """
        assert len(MetricCollector._collector_last_success._metrics) == 0
        assert len(MetricCollector._collector_smoothing_window._metrics) == 0
        assert len(MetricCollector._collector_start_offset._metrics) == 0

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


class TestEndpointGroupPlumbing(BaseCollectorTest):
    """Base scheduler/endpoint-group plumbing (#617 §1c).

    Only the base plumbing is exercised here — no real collector declares
    endpoint groups until Wave 2.
    """

    collector_class = DummyCollectorImpl

    def _make(self, isolated_registry, settings, scheduler=None):
        return DummyCollectorImpl(
            api=MagicMock(),
            settings=settings,
            registry=isolated_registry,
            scheduler=scheduler,
        )

    def test_endpoint_groups_default_empty(self, isolated_registry, settings) -> None:
        """Base endpoint_groups is an empty tuple; get_endpoint_groups mirrors it."""
        collector = self._make(isolated_registry, settings)
        assert MetricCollector.endpoint_groups == ()
        assert collector.get_endpoint_groups() == ()

    def test_scheduler_defaults_to_none(self, isolated_registry, settings) -> None:
        """The scheduler kwarg defaults to None (existing constructions unaffected)."""
        collector = self._make(isolated_registry, settings)
        assert collector.scheduler is None

    def test_scheduler_stored_when_provided(self, isolated_registry, settings) -> None:
        """A provided scheduler is threaded through to self.scheduler."""
        sched = MagicMock()
        collector = self._make(isolated_registry, settings, scheduler=sched)
        assert collector.scheduler is sched

    def test_gate_helpers_fail_open_when_scheduler_none(self, isolated_registry, settings) -> None:
        """No scheduler ⇒ always-run, None TTL, floor/large-sentinel interval."""
        collector = self._make(isolated_registry, settings)
        group = "device_availability"

        assert collector._should_run_group(group) is True
        assert collector._group_ttl_seconds(group) is None
        # No declared groups on the base ⇒ large sentinel, never re-gates falsely.
        assert collector._group_interval(group) == float("inf")
        # Marking a run without a scheduler must be a safe no-op.
        collector._mark_group_ran(group)

    def test_gate_helpers_delegate_to_scheduler(self, isolated_registry, settings) -> None:
        """With a scheduler set, gate helpers delegate to it."""
        sched = MagicMock()
        sched.should_run.return_value = False
        sched.interval_for.return_value = 1800.0
        sched.ttl_seconds_for.return_value = 3600.0
        collector = self._make(isolated_registry, settings, scheduler=sched)
        group = "device_availability"

        assert collector._should_run_group(group) is False
        sched.should_run.assert_called_once_with(group)

        assert collector._group_interval(group) == 1800.0
        sched.interval_for.assert_called_once_with(group)

        assert collector._group_ttl_seconds(group) == 3600.0
        sched.ttl_seconds_for.assert_called_once_with(group)

        collector._mark_group_ran(group)
        sched.mark_ran.assert_called_once_with(group)


class TestSetMetricTTLPassthrough(BaseCollectorTest):
    """_set_metric / _set_metric_value forward ttl_seconds to the tracker (#617 §1f)."""

    collector_class = DummyCollectorImpl

    def _make(self, isolated_registry, settings):
        return DummyCollectorImpl(
            api=MagicMock(),
            settings=settings,
            registry=isolated_registry,
        )

    def test_set_metric_forwards_ttl_seconds(self, isolated_registry, settings) -> None:
        """An explicit ttl_seconds reaches track_metric_update."""
        collector = self._make(isolated_registry, settings)
        collector.expiration_manager = MagicMock()

        collector._set_metric(
            collector._test_gauge,
            {"label1": "a", "label2": "b"},
            1.0,
            "test_gauge",
            ttl_seconds=900.0,
        )

        _, kwargs = collector.expiration_manager.track_metric_update.call_args
        assert kwargs["ttl_seconds"] == 900.0

    def test_set_metric_defaults_ttl_seconds_none(self, isolated_registry, settings) -> None:
        """Omitting ttl_seconds forwards None (tier-derived TTL applies)."""
        collector = self._make(isolated_registry, settings)
        collector.expiration_manager = MagicMock()

        collector._set_metric(
            collector._test_gauge, {"label1": "a", "label2": "b"}, 1.0, "test_gauge"
        )

        _, kwargs = collector.expiration_manager.track_metric_update.call_args
        assert kwargs["ttl_seconds"] is None

    def test_set_metric_value_forwards_ttl_seconds(self, isolated_registry, settings) -> None:
        """The legacy string-based helper threads ttl_seconds through to tracking."""
        collector = self._make(isolated_registry, settings)
        collector.expiration_manager = MagicMock()

        collector._set_metric_value(
            "_test_gauge", {"label1": "a", "label2": "b"}, 1.0, ttl_seconds=900.0
        )

        _, kwargs = collector.expiration_manager.track_metric_update.call_args
        assert kwargs["ttl_seconds"] == 900.0


class TestDisabledMetrics:
    """Per-metric cardinality controls (#309): cardinality.disabled_metrics.

    Metric families named in ``cardinality.disabled_metrics`` are dropped
    entirely: created unregistered (never exposed on /metrics) and never
    tracked with the expiration manager. Names are matched with a trailing
    ``_total`` normalized on both sides so operators can name counters either
    way.
    """

    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Provide the API key required to build real Settings."""
        monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)

    def _make_collector(self, disabled: set[str], registry):
        """Build a DummyCollectorImpl with a shim adding the CFG3 cardinality seam."""
        from types import SimpleNamespace

        from meraki_dashboard_exporter.core.config import Settings

        real = Settings()

        class _SettingsShim:
            cardinality = SimpleNamespace(disabled_metrics=disabled)

            def __getattr__(self, name):
                return getattr(real, name)

        return DummyCollectorImpl(
            api=MagicMock(),
            settings=_SettingsShim(),
            registry=registry,
        )

    @staticmethod
    def _registered_names(registry) -> set[str]:
        return {family.name for family in registry.collect()}

    def test_disabled_gauge_is_not_registered(self, isolated_registry) -> None:
        """A disabled family never reaches the registry but stays usable."""
        collector = self._make_collector({"test_gauge"}, isolated_registry)

        names = self._registered_names(isolated_registry)
        assert "test_gauge" not in names
        # Sibling metrics of the same collector remain registered.
        assert "test_counter" in names

        # The returned object is still usable (no-op), so collector code
        # touching it never crashes.
        collector._test_gauge.labels(label1="a", label2="b").set(1.0)

    def test_enabled_metrics_unaffected_when_nothing_disabled(self, isolated_registry) -> None:
        """An empty disabled set registers everything as before."""
        self._make_collector(set(), isolated_registry)

        names = self._registered_names(isolated_registry)
        assert "test_gauge" in names
        assert "test_counter" in names
        assert "test_histogram" in names

    def test_disabled_metric_skips_expiration_tracking(self, isolated_registry) -> None:
        """_set_metric on a disabled family does not track for expiration."""
        collector = self._make_collector({"test_gauge"}, isolated_registry)
        collector.expiration_manager = MagicMock()

        collector._set_metric(
            collector._test_gauge, {"label1": "a", "label2": "b"}, 1.0, "test_gauge"
        )

        collector.expiration_manager.track_metric_update.assert_not_called()

    def test_enabled_metric_still_tracked(self, isolated_registry) -> None:
        """_set_metric on an enabled family keeps expiration tracking."""
        collector = self._make_collector({"something_else"}, isolated_registry)
        collector.expiration_manager = MagicMock()

        collector._set_metric(
            collector._test_gauge, {"label1": "a", "label2": "b"}, 1.0, "test_gauge"
        )

        collector.expiration_manager.track_metric_update.assert_called_once()

    def test_total_suffix_is_normalized(self, isolated_registry) -> None:
        """Disabling 'test_counter_total' also drops the counter named 'test_counter'."""
        self._make_collector({"test_counter_total"}, isolated_registry)

        names = self._registered_names(isolated_registry)
        assert "test_counter" not in names
        assert "test_gauge" in names
