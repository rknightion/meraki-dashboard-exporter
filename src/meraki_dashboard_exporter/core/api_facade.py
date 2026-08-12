"""Single entry point for outbound Meraki SDK operations."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from .error_handling import validate_response_format


class MerakiApiFacade:
    """Stable async facade seam for synchronous Meraki SDK operations.

    The wave-1 implementation extends this passthrough with rate limiting,
    attempt instrumentation, bounded retry ownership and a per-fetch deadline.
    Callers depend only on :meth:`call`, whose signature is frozen.
    """

    async def call(
        self,
        operation: str,
        fn: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Run one synchronous SDK operation off the event loop and normalise it."""
        response = await asyncio.to_thread(fn, *args, **kwargs)
        return validate_response_format(response, type(response), operation)
