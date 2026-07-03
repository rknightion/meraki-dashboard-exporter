"""Unit tests for the collector registry."""

from __future__ import annotations

from meraki_dashboard_exporter.core.collector import MetricCollector
from meraki_dashboard_exporter.core.registry import (
    clear_registry,
    get_registered_collectors,
    register_collector,
)


class TestRegistry:
    """Test collector registry functionality."""

    def setup_method(self) -> None:
        """Clear registry before each test."""
        clear_registry()

    def teardown_method(self) -> None:
        """Clear registry after each test."""
        clear_registry()

    def test_register_collector(self) -> None:
        """Test registering a collector with the no-arg decorator."""

        @register_collector
        class TestCollector(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        collectors = get_registered_collectors()
        assert collectors == [TestCollector]

    def test_register_multiple_collectors(self) -> None:
        """Test registering multiple collectors preserves registration order."""

        @register_collector
        class Collector1(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        @register_collector
        class Collector2(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        @register_collector
        class Collector3(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        collectors = get_registered_collectors()
        assert collectors == [Collector1, Collector2, Collector3]

    def test_register_is_idempotent(self) -> None:
        """Registering the same class twice does not duplicate it."""

        @register_collector
        class TestCollector(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        register_collector(TestCollector)

        assert get_registered_collectors() == [TestCollector]

    def test_get_registered_collectors_returns_a_copy(self) -> None:
        """Mutating the returned list must not affect the registry."""

        @register_collector
        class TestCollector(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        collectors = get_registered_collectors()
        collectors.clear()

        assert get_registered_collectors() == [TestCollector]

    def test_clear_registry(self) -> None:
        """Test clearing the registry."""

        @register_collector
        class TestCollector(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        assert len(get_registered_collectors()) == 1

        clear_registry()
        assert get_registered_collectors() == []

    def test_decorator_preserves_class(self) -> None:
        """Test that the decorator doesn't modify the class."""

        @register_collector
        class TestCollector(MetricCollector):
            """Test collector docstring."""

            custom_attribute = "test"

            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        # Check that class attributes are preserved
        assert TestCollector.__doc__ == "Test collector docstring."
        assert TestCollector.custom_attribute == "test"
        assert TestCollector.__name__ == "TestCollector"
