"""Tests for SubCollectorMixin delegation."""

from __future__ import annotations

from unittest.mock import MagicMock

from meraki_dashboard_exporter.collectors.subcollector_mixin import SubCollectorMixin


class ConcreteSubCollector(SubCollectorMixin):
    """Concrete implementation for testing."""

    def __init__(self, parent: MagicMock) -> None:
        """Initialize with a mock parent."""
        self.parent = parent
        self.api = parent.api
        self.settings = parent.settings


class TestSubCollectorMixin:
    """Test SubCollectorMixin delegation behavior."""

    def test_set_metric_value_delegates_to_parent(self) -> None:
        """Test that _set_metric_value delegates to the parent collector."""
        parent = MagicMock()
        collector = ConcreteSubCollector(parent)
        collector._set_metric_value("_my_metric", {"org_id": "123"}, 42.0)
        parent._set_metric_value.assert_called_once_with("_my_metric", {"org_id": "123"}, 42.0)

    def test_set_metric_value_noop_when_parent_missing_method(self) -> None:
        """Test that _set_metric_value is a no-op when parent lacks the method."""
        parent = MagicMock(spec=[])
        # Bypass __init__ to avoid accessing restricted parent attributes
        collector = object.__new__(ConcreteSubCollector)
        collector.parent = parent
        collector._set_metric_value("_my_metric", {"org_id": "123"}, 42.0)

    def test_track_api_call_delegates_to_parent(self) -> None:
        """Test that _track_api_call delegates to the parent collector."""
        parent = MagicMock()
        collector = ConcreteSubCollector(parent)
        collector._track_api_call("getOrganizationDevices")
        parent._track_api_call.assert_called_once_with("getOrganizationDevices")

    def test_track_api_call_noop_when_parent_missing_method(self) -> None:
        """Test that _track_api_call is a no-op when parent lacks the method."""
        parent = MagicMock(spec=[])
        # Bypass __init__ to avoid accessing restricted parent attributes
        collector = object.__new__(ConcreteSubCollector)
        collector.parent = parent
        collector._track_api_call("getOrganizationDevices")

    def test_update_api_sets_api_attribute(self) -> None:
        """Test that update_api sets the api attribute on the collector."""
        parent = MagicMock()
        collector = ConcreteSubCollector(parent)
        new_api = MagicMock()
        collector.update_api(new_api)
        assert collector.api is new_api
