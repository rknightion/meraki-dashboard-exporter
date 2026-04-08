"""Tests for MTCollector factory methods."""

from __future__ import annotations

from unittest.mock import MagicMock

from meraki_dashboard_exporter.collectors.devices.mt import MTCollector


class TestMTCollectorFactory:
    """Test MTCollector creation modes."""

    def test_as_subcollector_sets_parent(self) -> None:
        """as_subcollector creates a collector with the given parent."""
        parent = MagicMock()
        parent.api = MagicMock()
        parent.settings = MagicMock()
        collector = MTCollector.as_subcollector(parent)
        assert collector.parent is parent
        assert collector.api is parent.api

    def test_as_standalone_has_no_parent_initially(self) -> None:
        """as_standalone creates a collector without a parent."""
        api = MagicMock()
        settings = MagicMock()
        collector = MTCollector.as_standalone(api=api, settings=settings)
        assert collector.api is api
        assert collector.settings is settings
        assert collector.parent is None

    def test_as_standalone_accepts_parent_reassignment(self) -> None:
        """Standalone collectors accept parent assignment for metric access."""
        api = MagicMock()
        settings = MagicMock()
        parent_proxy = MagicMock()
        collector = MTCollector.as_standalone(api=api, settings=settings)
        collector.parent = parent_proxy
        assert collector.parent is parent_proxy

    def test_no_standalone_mode_flag(self) -> None:
        """Standalone mode should not use a _standalone_mode flag."""
        api = MagicMock()
        settings = MagicMock()
        collector = MTCollector.as_standalone(api=api, settings=settings)
        assert not hasattr(collector, "_standalone_mode")
