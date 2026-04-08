"""Base organization collector with common functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.logging import get_logger
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from ...core.config import Settings
    from ...services.inventory import OrganizationInventory
    from ..organization import OrganizationCollector

logger = get_logger(__name__)


class BaseOrganizationCollector(SubCollectorMixin):
    """Base class for organization sub-collectors."""

    def __init__(self, parent: OrganizationCollector) -> None:
        """Initialize base organization collector.

        Parameters
        ----------
        parent : OrganizationCollector
            Parent OrganizationCollector instance that has metrics defined.

        """
        self.parent = parent
        self.api = parent.api
        self.settings: Settings = parent.settings
        self.inventory: OrganizationInventory | None = getattr(parent, "inventory", None)
