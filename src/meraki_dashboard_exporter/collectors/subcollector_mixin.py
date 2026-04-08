"""Mixin providing common sub-collector delegation patterns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..core.logging import get_logger

if TYPE_CHECKING:
    from meraki import DashboardAPI

logger = get_logger(__name__)


class SubCollectorMixin:
    """Mixin for sub-collectors that delegate metrics to a parent collector.

    Provides consistent implementations of _set_metric_value, _track_api_call,
    and update_api so all sub-collector base classes share the same delegation
    logic instead of each implementing their own version.

    Requires the using class to have:
    - self.parent: The parent collector instance
    - self.api: The Meraki DashboardAPI instance

    """

    parent: Any
    api: DashboardAPI

    def _set_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Set a metric value by delegating to the parent collector.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute on the parent.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. If None, the metric will not be updated.

        """
        if hasattr(self.parent, "_set_metric_value"):
            self.parent._set_metric_value(metric_name, labels, value)

    def _track_api_call(self, method_name: str) -> None:
        """Track an API call by delegating to the parent collector.

        Parameters
        ----------
        method_name : str
            Name of the API method being called.

        """
        if hasattr(self.parent, "_track_api_call"):
            self.parent._track_api_call(method_name)

    def update_api(self, api: DashboardAPI) -> None:
        """Update the API client instance.

        Parameters
        ----------
        api : DashboardAPI
            New API client instance.

        """
        self.api = api
