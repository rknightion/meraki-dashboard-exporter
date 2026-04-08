"""Per-organization health tracking for graceful degradation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .logging import get_logger

logger = get_logger(__name__)


@dataclass
class OrgHealth:
    """Health state for a single organization."""

    org_id: str
    org_name: str
    consecutive_failures: int = 0
    last_success: float = field(default=0.0)
    last_failure: float = field(default=0.0)
    backoff_until: float = field(default=0.0)


class OrgHealthTracker:
    """Tracks per-organization collection health for graceful degradation.

    After N consecutive failures for an org, exponentially backs off
    collection for that org while continuing normal collection for healthy orgs.

    Parameters
    ----------
    max_consecutive_failures : int
        Number of consecutive failures before backoff begins.
    base_backoff : float
        Initial backoff duration in seconds.
    max_backoff : float
        Maximum backoff duration in seconds.

    """

    def __init__(
        self,
        max_consecutive_failures: int = 5,
        base_backoff: float = 60.0,
        max_backoff: float = 3600.0,
    ) -> None:
        """Initialize the tracker with backoff configuration."""
        self._orgs: dict[str, OrgHealth] = {}
        self.max_consecutive_failures = max_consecutive_failures
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff

    def record_success(self, org_id: str, org_name: str = "") -> None:
        """Record a successful collection for an org.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name (used to populate health record on first creation).

        """
        health = self._get_or_create(org_id, org_name)
        was_backed_off = health.consecutive_failures >= self.max_consecutive_failures
        health.consecutive_failures = 0
        health.last_success = time.time()
        health.backoff_until = 0.0
        if was_backed_off:
            logger.warning(
                "Organization recovered from backoff",
                org_id=org_id,
                org_name=org_name,
            )

    def record_failure(self, org_id: str, org_name: str = "") -> None:
        """Record a failed collection for an org.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name (used to populate health record on first creation).

        """
        health = self._get_or_create(org_id, org_name)
        health.consecutive_failures += 1
        health.last_failure = time.time()
        if health.consecutive_failures >= self.max_consecutive_failures:
            backoff = min(
                self.base_backoff
                * (2 ** (health.consecutive_failures - self.max_consecutive_failures)),
                self.max_backoff,
            )
            health.backoff_until = time.time() + backoff
            logger.warning(
                "Organization entering backoff",
                org_id=org_id,
                org_name=org_name,
                consecutive_failures=health.consecutive_failures,
                backoff_seconds=backoff,
            )

    def should_collect(self, org_id: str) -> bool:
        """Check if an org should be collected (not in backoff).

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        bool
            True if collection should proceed, False if org is in backoff.

        """
        health = self._orgs.get(org_id)
        if health is None:
            return True
        return time.time() >= health.backoff_until

    def get_health(self, org_id: str) -> OrgHealth | None:
        """Get health state for an org.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        OrgHealth | None
            Health state for the org, or None if no record exists.

        """
        return self._orgs.get(org_id)

    def _get_or_create(self, org_id: str, org_name: str) -> OrgHealth:
        if org_id not in self._orgs:
            self._orgs[org_id] = OrgHealth(org_id=org_id, org_name=org_name)
        elif org_name and not self._orgs[org_id].org_name:
            self._orgs[org_id].org_name = org_name
        return self._orgs[org_id]
