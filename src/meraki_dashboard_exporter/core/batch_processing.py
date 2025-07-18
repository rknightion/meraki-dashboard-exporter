"""Batch processing utilities for collectors.

This module provides utilities for processing items in batches with
error handling and logging.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, TypeVar

from .logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


async def process_in_batches_with_errors(
    items: list[T],
    process_func: Callable[[T], Coroutine[Any, Any, R]],
    batch_size: int = 10,
    delay_between_batches: float = 0.5,
    item_description: str = "item",
    error_context_func: Callable[[T], dict[str, Any]] | None = None,
) -> list[tuple[T, R | Exception]]:
    """Process items in batches with error handling and logging.

    Parameters
    ----------
    items : list[T]
        Items to process.
    process_func : Callable[[T], Coroutine[Any, Any, R]]
        Async function to process each item.
    batch_size : int
        Number of items to process concurrently.
    delay_between_batches : float
        Delay in seconds between batches.
    item_description : str
        Description of items for logging (e.g., "device", "network").
    error_context_func : Callable[[T], dict[str, Any]] | None
        Optional function to extract error context from item.

    Returns
    -------
    list[tuple[T, R | Exception]]
        List of (item, result) tuples where result is either the return value
        or an exception if processing failed.

    """
    results: list[tuple[T, R | Exception]] = []
    total_items = len(items)

    for i in range(0, total_items, batch_size):
        batch = items[i : i + batch_size]
        batch_end = min(i + batch_size, total_items)

        logger.debug(
            f"Processing batch of {item_description}s",
            batch_start=i + 1,
            batch_end=batch_end,
            total=total_items,
        )

        # Create tasks for batch
        tasks = [process_func(item) for item in batch]

        # Process batch concurrently
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for item, result in zip(batch, batch_results, strict=False):
            if isinstance(result, BaseException):
                # Extract context for error logging
                context = {"error": str(result), "error_type": type(result).__name__}
                if error_context_func:
                    context.update(error_context_func(item))

                logger.error(f"Failed to process {item_description}", **context)

            # Only append if it's the expected type or Exception
            if not isinstance(result, BaseException) or isinstance(result, Exception):
                results.append((item, result))

        # Delay between batches (except for the last batch)
        if i + batch_size < total_items and delay_between_batches > 0:
            await asyncio.sleep(delay_between_batches)

    return results


async def process_grouped_items(
    items_by_group: dict[str, list[T]],
    process_func: Callable[[T], Coroutine[Any, Any, R]],
    batch_size: int = 10,
    delay_between_batches: float = 0.5,
    group_description: str = "group",
    item_description: str = "item",
    error_context_func: Callable[[T], dict[str, Any]] | None = None,
    skip_groups: set[str] | None = None,
) -> dict[str, list[tuple[T, R | Exception]]]:
    """Process grouped items in batches.

    Parameters
    ----------
    items_by_group : dict[str, list[T]]
        Items grouped by some key.
    process_func : Callable[[T], Coroutine[Any, Any, R]]
        Async function to process each item.
    batch_size : int
        Number of items to process concurrently within each group.
    delay_between_batches : float
        Delay in seconds between batches.
    group_description : str
        Description of groups for logging (e.g., "device type").
    item_description : str
        Description of items for logging (e.g., "device").
    error_context_func : Callable[[T], dict[str, Any]] | None
        Optional function to extract error context from item.
    skip_groups : set[str] | None
        Groups to skip processing.

    Returns
    -------
    dict[str, list[tuple[T, R | Exception]]]
        Results grouped by the same keys as input.

    """
    results: dict[str, list[tuple[T, R | Exception]]] = {}
    skip_groups = skip_groups or set()

    for group_key, group_items in items_by_group.items():
        if group_key in skip_groups:
            logger.debug(f"Skipping {group_description}", group=group_key)
            continue

        if not group_items:
            continue

        logger.debug(
            f"Processing {group_description}",
            group=group_key,
            count=len(group_items),
        )

        group_results = await process_in_batches_with_errors(
            group_items,
            process_func,
            batch_size=batch_size,
            delay_between_batches=delay_between_batches,
            item_description=f"{group_key} {item_description}",
            error_context_func=error_context_func,
        )

        results[group_key] = group_results

    return results


def extract_successful_results[T, R](
    results: list[tuple[T, R | Exception]],
) -> list[R]:
    """Extract successful results from batch processing results.

    Parameters
    ----------
    results : list[tuple[T, R | Exception]]
        Results from batch processing.

    Returns
    -------
    list[R]
        List of successful results, excluding exceptions.

    """
    return [result for item, result in results if not isinstance(result, Exception)]
