"""Collector registry for automatic collector registration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from ..core.constants import UpdateTier
from ..core.logging import get_logger

if TYPE_CHECKING:
    from ..core.collector import MetricCollector

logger = get_logger(__name__)

# Type variable for collector classes
T = TypeVar("T", bound="MetricCollector")

# Global registry of all collectors
_COLLECTOR_REGISTRY: dict[UpdateTier, list[type[MetricCollector]]] = {
    UpdateTier.FAST: [],
    UpdateTier.MEDIUM: [],
    UpdateTier.SLOW: [],
}


def register_collector(tier: UpdateTier | None = None) -> Callable[[type[T]], type[T]]:
    """Decorator to automatically register collectors.

    Parameters
    ----------
    tier : UpdateTier | None
        The update tier for the collector. If None, uses the collector's
        default update_tier class attribute.

    Returns
    -------
    callable
        Decorator function that registers the collector.

    Examples
    --------
    >>> @register_collector(UpdateTier.FAST)
    ... class MyFastCollector(MetricCollector):
    ...     pass

    >>> @register_collector()  # Uses collector's update_tier attribute
    ... class MyCollector(MetricCollector):
    ...     update_tier = UpdateTier.MEDIUM

    """

    def decorator(cls: T) -> T:
        """Register the collector class."""
        # Determine the tier to use
        collector_tier = tier
        if collector_tier is None:
            # Use the class's update_tier attribute
            collector_tier = getattr(cls, "update_tier", UpdateTier.MEDIUM)

        # Override the class's update_tier if tier was explicitly provided
        if tier is not None:
            cls.update_tier = tier

        # Register the collector
        _COLLECTOR_REGISTRY[collector_tier].append(cls)
        logger.debug(
            "Registered collector",
            collector=cls.__name__,
            tier=collector_tier.value,
        )

        return cls

    return decorator


def get_registered_collectors() -> dict[UpdateTier, list[type[MetricCollector]]]:
    """Get all registered collectors organized by tier.

    Returns
    -------
    dict[UpdateTier, list[type[MetricCollector]]]
        Dictionary mapping update tiers to lists of collector classes.

    """
    return _COLLECTOR_REGISTRY.copy()


def get_collectors_for_tier(tier: UpdateTier) -> list[type[MetricCollector]]:
    """Get all collectors registered for a specific tier.

    Parameters
    ----------
    tier : UpdateTier
        The update tier to get collectors for.

    Returns
    -------
    list[type[MetricCollector]]
        List of collector classes for the specified tier.

    """
    return _COLLECTOR_REGISTRY.get(tier, []).copy()


def clear_registry() -> None:
    """Clear the collector registry.

    This is mainly useful for testing purposes.
    """
    for tier_list in _COLLECTOR_REGISTRY.values():
        tier_list.clear()
    logger.debug("Cleared collector registry")
