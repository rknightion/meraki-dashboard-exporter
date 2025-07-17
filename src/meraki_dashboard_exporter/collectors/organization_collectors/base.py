"""Base organization collector with common functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.logging import get_logger

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...core.config import Settings
    from ..organization import OrganizationCollector

logger = get_logger(__name__)


class BaseOrganizationCollector:
    """Base class for organization sub-collectors."""

    def __init__(self, parent: OrganizationCollector) -> None:
        """Initialize base organization collector.

        Parameters
        ----------
        parent : OrganizationCollector
            Parent OrganizationCollector instance that has metrics defined.

        """
        self.parent = parent
        self.api: DashboardAPI = parent.api
        self.settings: Settings = parent.settings

    def _track_api_call(self, method_name: str) -> None:
        """Track API call in parent collector.

        Parameters
        ----------
        method_name : str
            Name of the API method being called.

        """
        if hasattr(self.parent, "_track_api_call"):
            self.parent._track_api_call(method_name)

    def _set_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Safely set a metric value with validation.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. If None, the metric will not be updated.

        """
        if hasattr(self.parent, "_set_metric_value"):
            self.parent._set_metric_value(metric_name, labels, value)
        else:
            # Fall back to direct metric setting
            if value is None:
                return
            metric = getattr(self.parent, metric_name, None)
            if metric:
                try:
                    metric.labels(**labels).set(value)
                except Exception:
                    logger.exception(
                        "Failed to set metric value",
                        metric_name=metric_name,
                        labels=labels,
                        value=value,
                    )
