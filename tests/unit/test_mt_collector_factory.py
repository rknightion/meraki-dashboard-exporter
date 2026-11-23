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
