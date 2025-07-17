"""Unit tests for the collector registry."""

from __future__ import annotations

from meraki_dashboard_exporter.core.collector import MetricCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.registry import (
    clear_registry,
    get_collectors_for_tier,
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

    def test_register_collector_with_explicit_tier(self) -> None:
        """Test registering a collector with explicit tier."""

        @register_collector(UpdateTier.FAST)
        class TestFastCollector(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        # Check that collector is registered in FAST tier
        fast_collectors = get_collectors_for_tier(UpdateTier.FAST)
        assert len(fast_collectors) == 1
        assert fast_collectors[0] == TestFastCollector

        # Check that update_tier was set correctly
        assert TestFastCollector.update_tier == UpdateTier.FAST

    def test_register_collector_with_default_tier(self) -> None:
        """Test registering a collector using its default tier."""

        @register_collector()
        class TestDefaultCollector(MetricCollector):
            update_tier = UpdateTier.SLOW

            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        # Check that collector is registered in SLOW tier
        slow_collectors = get_collectors_for_tier(UpdateTier.SLOW)
        assert len(slow_collectors) == 1
        assert slow_collectors[0] == TestDefaultCollector

    def test_register_multiple_collectors(self) -> None:
        """Test registering multiple collectors in different tiers."""

        @register_collector(UpdateTier.FAST)
        class FastCollector1(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        @register_collector(UpdateTier.FAST)
        class FastCollector2(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        @register_collector(UpdateTier.MEDIUM)
        class MediumCollector(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        # Check registrations
        fast_collectors = get_collectors_for_tier(UpdateTier.FAST)
        assert len(fast_collectors) == 2
        assert FastCollector1 in fast_collectors
        assert FastCollector2 in fast_collectors

        medium_collectors = get_collectors_for_tier(UpdateTier.MEDIUM)
        assert len(medium_collectors) == 1
        assert medium_collectors[0] == MediumCollector

    def test_get_registered_collectors(self) -> None:
        """Test getting all registered collectors."""

        @register_collector(UpdateTier.FAST)
        class TestFastCollector(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        @register_collector(UpdateTier.SLOW)
        class TestSlowCollector(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        all_collectors = get_registered_collectors()
        assert len(all_collectors) == 3  # FAST, MEDIUM, SLOW tiers
        assert len(all_collectors[UpdateTier.FAST]) == 1
        assert len(all_collectors[UpdateTier.SLOW]) == 1
        assert len(all_collectors[UpdateTier.MEDIUM]) == 0

    def test_clear_registry(self) -> None:
        """Test clearing the registry."""

        @register_collector(UpdateTier.MEDIUM)
        class TestCollector(MetricCollector):
            def _initialize_metrics(self) -> None:
                pass

            async def _collect_impl(self) -> None:
                pass

        # Verify collector is registered
        assert len(get_collectors_for_tier(UpdateTier.MEDIUM)) == 1

        # Clear and verify
        clear_registry()
        assert len(get_collectors_for_tier(UpdateTier.MEDIUM)) == 0
        all_collectors = get_registered_collectors()
        assert all(len(collectors) == 0 for collectors in all_collectors.values())

    def test_decorator_preserves_class(self) -> None:
        """Test that the decorator doesn't modify the class."""

        @register_collector(UpdateTier.FAST)
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
