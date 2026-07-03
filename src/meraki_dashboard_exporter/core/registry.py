"""Collector registry for automatic collector registration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.logging import get_logger

if TYPE_CHECKING:
    from ..core.collector import MetricCollector

logger = get_logger(__name__)

# Global flat registry of all top-level collectors. Since the FAST/MEDIUM/SLOW
# tier model was removed (#631), every collector runs its own endpoint-group
# clocked loop; there is no per-tier grouping any more.
_COLLECTOR_REGISTRY: list[type[MetricCollector]] = []


def register_collector[T](cls: T) -> T:
    """Decorator to automatically register a collector with the CollectorManager.

    Enables automatic discovery of collectors without manual registration: when
    a module containing a decorated collector is imported, the collector is
    added to the global registry. Sub-collectors must NOT use this decorator.

    Parameters
    ----------
    cls : type[MetricCollector]
        The collector class being registered (used directly as ``@register_collector``).

    Returns
    -------
    type[MetricCollector]
        The same class, unchanged.

    Examples
    --------
    >>> @register_collector
    ... class MyCollector(MetricCollector):
    ...     async def _collect_impl(self) -> None:
    ...         pass

    """
    if cls not in _COLLECTOR_REGISTRY:
        _COLLECTOR_REGISTRY.append(cls)  # type: ignore[arg-type]
        logger.debug(
            "Registered collector",
            collector=cls.__name__,  # type: ignore[attr-defined]
        )
    return cls


def get_registered_collectors() -> list[type[MetricCollector]]:
    """Get all registered collector classes.

    Returns
    -------
    list[type[MetricCollector]]
        The registered collector classes, in registration order.

    """
    return list(_COLLECTOR_REGISTRY)


def clear_registry() -> None:
    """Clear the collector registry.

    This is mainly useful for testing purposes.
    """
    _COLLECTOR_REGISTRY.clear()
    logger.debug("Cleared collector registry")
