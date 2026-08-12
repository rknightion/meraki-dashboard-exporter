"""Per-organization health tracking for graceful degradation.

Backoff is aware of multiple *failure domains* (#547). Several collectors run
against the same organizations every cycle -- the organization collector, the
device collector, and the network-health collector -- and any one of them
finding an org's endpoints broken is grounds to back that org off, even if the
other domains are healthy (or, for the org collector, disabled entirely).

To keep this multi-writer design race-free, each writing collector records under
its own **source** bucket (see ``SOURCE_*``). The tracker keeps an independent
consecutive-failure counter per source in ``OrgHealth.source_failures``; the
effective ``consecutive_failures`` that drives backoff is the MAX across those
buckets (conservative "any recent domain failure => backoff"). Because each
collector only ever touches its own bucket, and every ``record_*`` call runs to
completion without awaiting, concurrent writers on the single asyncio event loop
never interleave a read-modify-write on the same counter.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .error_handling import ErrorCategory
from .logging import get_logger

logger = get_logger(__name__)

# Failure-domain sources. Each writing collector records its per-org verdict
# under its own source so backoff is aware of every domain, not just the org
# collector's. New sources can be added freely -- the effective failure count is
# the max across whatever sources have been recorded.
SOURCE_ORGANIZATION = "organization"
SOURCE_DEVICE = "device"
SOURCE_NETWORK_HEALTH = "network_health"
SOURCE_GLOBAL = "global"


@dataclass
class OrgHealth:
    """Health state for a single organization.

    Attributes
    ----------
    org_id : str
        Organization ID.
    org_name : str
        Organization name.
    source_failures : dict[str, int]
        Per-source consecutive-failure counters. Each writing collector owns one
        entry keyed by its ``SOURCE_*`` constant. The effective
        ``consecutive_failures`` is the max across these (see property).
    last_success : float
        Unix timestamp of the most recent success in any domain.
    last_failure : float
        Unix timestamp of the most recent failure in any domain.
    backoff_until : float
        Unix timestamp until which this org is backed off (0.0 = not backed off).

    """

    org_id: str
    org_name: str
    source_failures: dict[str, int] = field(default_factory=dict)
    source_backoff_until: dict[str, float] = field(default_factory=dict)
    source_categories: dict[str, ErrorCategory] = field(default_factory=dict)
    last_success: float = field(default=0.0)
    last_failure: float = field(default=0.0)
    backoff_until: float = field(default=0.0)

    @property
    def consecutive_failures(self) -> int:
        """Effective consecutive failures: the max across all failure domains.

        A persistent failure in ANY single domain is enough to drive backoff, so
        the effective streak is the largest per-source streak. Returns 0 when no
        source has recorded a failure.
        """
        return max(self.source_failures.values(), default=0)


class OrgHealthTracker:
    """Tracks per-organization collection health for graceful degradation.

    After N consecutive failures for an org (in any single failure domain),
    exponentially backs off collection for that org while continuing normal
    collection for healthy orgs.

    Multiple collectors write into one shared tracker, each under its own
    ``source`` (#547). See the module docstring for the race-free design.

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

    def record_success(
        self,
        org_id: str,
        org_name: str = "",
        source: str = SOURCE_ORGANIZATION,
    ) -> None:
        """Record a successful collection for an org in one failure domain.

        Resets only this ``source``'s failure counter. Backoff is cleared only
        when the effective (max across domains) streak drops back below the
        threshold -- a healthy cycle in one domain must not clear backoff that a
        still-failing domain is holding (#547).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name (used to populate health record on first creation).
        source : str
            Failure domain reporting the success (one of ``SOURCE_*``).

        """
        health = self._get_or_create(org_id, org_name)
        was_backed_off = health.source_failures.get(source, 0) >= self.max_consecutive_failures
        health.source_failures[source] = 0
        health.source_backoff_until[source] = 0.0
        health.source_categories.pop(source, None)
        global_category = health.source_categories.get(SOURCE_GLOBAL)
        if global_category is ErrorCategory.API_AUTH_ERROR:
            health.source_failures[SOURCE_GLOBAL] = 0
            health.source_backoff_until[SOURCE_GLOBAL] = 0.0
            health.source_categories.pop(SOURCE_GLOBAL, None)
        elif global_category in {ErrorCategory.CONNECTIVITY, ErrorCategory.TIMEOUT}:
            active_connectivity_sources = [
                domain
                for domain, domain_category in health.source_categories.items()
                if domain != SOURCE_GLOBAL
                and domain_category in {ErrorCategory.CONNECTIVITY, ErrorCategory.TIMEOUT}
                and health.source_failures.get(domain, 0) >= self.max_consecutive_failures
            ]
            if len(active_connectivity_sources) < 2:
                health.source_failures[SOURCE_GLOBAL] = 0
                health.source_backoff_until[SOURCE_GLOBAL] = 0.0
                health.source_categories.pop(SOURCE_GLOBAL, None)
        health.last_success = time.time()
        health.backoff_until = max(health.source_backoff_until.values(), default=0.0)
        if was_backed_off:
            logger.warning(
                "Organization failure domain recovered from backoff",
                org_id=org_id,
                org_name=org_name,
                source=source,
            )

    def record_failure(
        self,
        org_id: str,
        org_name: str = "",
        source: str = SOURCE_ORGANIZATION,
        category: ErrorCategory | None = None,
    ) -> None:
        """Record a failed collection for an org in one failure domain.

        Increments only this ``source``'s failure counter. Backoff engages once
        the effective (max across domains) streak reaches the threshold, so a
        persistent failure in ANY domain backs the org off (#547).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name (used to populate health record on first creation).
        source : str
            Failure domain reporting the failure (one of ``SOURCE_*``).
        category : ErrorCategory | None
            Failure classification. Endpoint-unavailable outcomes do not
            advance the health streak.

        """
        health = self._get_or_create(org_id, org_name)
        if category is ErrorCategory.API_AUTH_ERROR:
            source = SOURCE_GLOBAL
        if category is ErrorCategory.API_NOT_AVAILABLE:
            logger.debug(
                "Endpoint unavailable for organization; not counting against health",
                org_id=org_id,
                org_name=org_name,
                source=source,
            )
            return
        if category is not None:
            health.source_categories[source] = category
        health.source_failures[source] = health.source_failures.get(source, 0) + 1
        health.last_failure = time.time()
        failures = health.source_failures[source]
        if failures >= self.max_consecutive_failures:
            backoff = min(
                self.base_backoff * (2 ** (failures - self.max_consecutive_failures)),
                self.max_backoff,
            )
            health.source_backoff_until[source] = time.time() + backoff
            health.backoff_until = max(health.source_backoff_until.values(), default=0.0)
            logger.warning(
                "Organization entering backoff",
                org_id=org_id,
                org_name=org_name,
                source=source,
                consecutive_failures=failures,
                backoff_seconds=backoff,
            )

        if category in {ErrorCategory.CONNECTIVITY, ErrorCategory.TIMEOUT}:
            active_connectivity_sources = [
                domain
                for domain, domain_category in health.source_categories.items()
                if domain != SOURCE_GLOBAL
                and domain_category in {ErrorCategory.CONNECTIVITY, ErrorCategory.TIMEOUT}
                and health.source_failures.get(domain, 0) >= self.max_consecutive_failures
            ]
            if len(active_connectivity_sources) >= 2:
                health.source_failures[SOURCE_GLOBAL] = max(
                    health.source_failures[domain] for domain in active_connectivity_sources
                )
                health.source_backoff_until[SOURCE_GLOBAL] = max(
                    health.source_backoff_until.get(domain, 0.0)
                    for domain in active_connectivity_sources
                )
                health.source_categories[SOURCE_GLOBAL] = category
                health.backoff_until = max(health.source_backoff_until.values(), default=0.0)

    def should_collect(self, org_id: str, *, source: str | None = None) -> bool:
        """Check if an org should be collected (not in backoff).

        Parameters
        ----------
        org_id : str
            Organization ID.
        source : str | None
            Optional failure domain. When supplied, only that domain's
            backoff is consulted; omitted preserves the aggregate view.

        Returns
        -------
        bool
            True if collection should proceed, False if org is in backoff.

        """
        health = self._orgs.get(org_id)
        if health is None:
            return True
        backoff_until = health.backoff_until
        if source is not None:
            # The organization source is reserved for an org-wide verdict
            # (authentication or multi-domain connectivity). It therefore
            # suppresses every domain, while ordinary source failures remain
            # local to their source.
            backoff_until = max(
                health.source_backoff_until.get(source, 0.0),
                health.source_backoff_until.get(SOURCE_GLOBAL, 0.0),
            )
        return time.time() >= backoff_until

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
