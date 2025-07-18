"""Collector registry for automatic collector registration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from ..core.constants import UpdateTier
from ..core.logging import get_logger

if TYPE_CHECKING:
    from ..core.collector import MetricCollector

logger = get_logger(__name__)

# Type variable for collector classes - using Any to avoid mypy issues
T = TypeVar("T")

# Global registry of all collectors
_COLLECTOR_REGISTRY: dict[UpdateTier, list[type[MetricCollector]]] = {
    UpdateTier.FAST: [],
    UpdateTier.MEDIUM: [],
    UpdateTier.SLOW: [],
}


def register_collector(tier: UpdateTier | None = None) -> Callable[[T], T]:
    """Decorator to automatically register collectors with the CollectorManager.

    This decorator enables automatic discovery of collectors without manual
    registration. When a module containing a decorated collector is imported,
    the collector is automatically added to the global registry.

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
    Basic usage with explicit tier:
    >>> @register_collector(UpdateTier.FAST)
    ... class MyFastCollector(MetricCollector):
    ...     def _collect_impl(self) -> None:
    ...         # Collect metrics every 60 seconds
    ...         pass

    Using collector's default tier:
    >>> @register_collector()  # Uses update_tier attribute
    ... class MyCollector(MetricCollector):
    ...     update_tier = UpdateTier.MEDIUM
    ...
    ...     def _collect_impl(self) -> None:
    ...         # Collect metrics every 5 minutes
    ...         pass

    Complete collector example:
    >>> @register_collector(UpdateTier.SLOW)
    ... class ConfigCollector(MetricCollector):
    ...     '''Collects configuration metrics every 15 minutes.'''
    ...
    ...     def _initialize_metrics(self) -> None:
    ...         self._config_changes = self._create_counter(
    ...             "config_changes_total",
    ...             "Total configuration changes"
    ...         )
    ...
    ...     async def _collect_impl(self) -> None:
    ...         changes = await self._fetch_config_changes()
    ...         self._config_changes.inc(len(changes))

    Notes
    -----
    - Registration happens at import time when the module is loaded
    - The CollectorManager discovers collectors by importing all modules
    - Collectors are instantiated only when the manager starts
    - Each collector can only be registered once per tier
    - Sub-collectors should NOT use this decorator

    How it Works
    ------------
    1. Module imported → Decorator executes → Collector added to registry
    2. CollectorManager.initialize() → Imports all collector modules
    3. CollectorManager._initialize_collectors() → Creates instances
    4. Collectors are grouped by tier for scheduled execution

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
            cls.update_tier = tier  # type: ignore[attr-defined]

        # Register the collector
        _COLLECTOR_REGISTRY[collector_tier].append(cls)  # type: ignore[arg-type]
        logger.debug(
            "Registered collector",
            collector=cls.__name__,  # type: ignore[attr-defined]
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
