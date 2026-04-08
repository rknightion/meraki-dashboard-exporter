"""Base network health collector with common functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.logging import get_logger
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from ...core.config import Settings
    from ..network_health import NetworkHealthCollector

logger = get_logger(__name__)


class BaseNetworkHealthCollector(SubCollectorMixin):
    """Base class for network health sub-collectors."""

    def __init__(self, parent: NetworkHealthCollector) -> None:
        """Initialize base network health collector.

        Parameters
        ----------
        parent : NetworkHealthCollector
            Parent NetworkHealthCollector instance that has metrics defined.

        """
        self.parent = parent
        self.api = parent.api
        self.settings: Settings = parent.settings
