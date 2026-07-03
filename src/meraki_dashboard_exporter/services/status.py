"""Status snapshot dataclasses for the /status health dashboard.

These dataclasses define the data model used to report system health,
collector state, API health, and data freshness information.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from prometheus_client import REGISTRY
from prometheus_client.registry import CollectorRegistry

from ..core.constants import UpdateTier
from ..core.constants.metrics_constants import NetworkMetricName
from ..core.org_health import OrgHealth

if TYPE_CHECKING:
    from ..api.client import AsyncMerakiClient
    from ..collectors.manager import CollectorManager
    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager
    from ..core.webhook_handler import WebhookHandler


def _compute_staleness(
    last_success_time: float | None,
    tier_interval: int,
    now: float | None = None,
) -> str:
    """Compute staleness category based on time since last success.

    Parameters
    ----------
    last_success_time : float | None
        Unix timestamp of last successful collection, or None if never succeeded.
    tier_interval : int
        The collection interval for this tier in seconds.
    now : float | None
        Current time as unix timestamp. Defaults to time.time().

    Returns
    -------
    str
        "ok", "warning", or "stale".

    """
    if last_success_time is None:
        return "stale"
    if now is None:
        now = time.time()
    age = now - last_success_time
    if age <= tier_interval:
        return "ok"
    if age <= tier_interval * 2:
        return "warning"
    return "stale"


def _format_time_ago(timestamp: float | None, now: float | None = None) -> str:
    """Format a unix timestamp as a human-readable relative time.

    Parameters
    ----------
    timestamp : float | None
        Unix timestamp, or None.
    now : float | None
        Current time as unix timestamp. Defaults to time.time().

    Returns
    -------
    str
        Human-readable string like "30s ago", "5m ago", "2h ago", or "Never".

    """
    if timestamp is None:
        return "Never"
    if now is None:
        now = time.time()
    age = int(now - timestamp)
    if age < 60:
        return f"{age}s ago"
    if age < 3600:
        return f"{age // 60}m ago"
    return f"{age // 3600}h ago"


@dataclass
class CollectorStatus:
    """Status of a single collector."""

    name: str
    tier: str
    total_runs: int
    total_successes: int
    total_failures: int
    success_rate: float
    failure_streak: int
    last_success_time: float | None
    last_success_ago: str
    is_running: bool
    staleness: str


@dataclass
class ApiHealthStatus:
    """Health status of API interactions."""

    total_calls: int
    throttle_events: int
    per_org_rate_limits: list[dict[str, Any]]
    authenticated: bool | None = None


@dataclass
class DataFreshnessStatus:
    """Freshness status of collected metric data."""

    total_tracked_metrics: int
    by_collector: dict[str, int]
    ttl_multiplier: float


@dataclass
class OrgHealthStatus:
    """Health status for a single organization."""

    org_id: str
    org_name: str
    consecutive_failures: int
    in_backoff: bool
    backoff_remaining_seconds: float


@dataclass
class NetworkFilterStatus:
    """Effective state of the configured ``NetworkFilter`` (#311).

    Surfaces both the parsed filter rules (so an operator can see whether a
    glob/tag typo was parsed as intended) and the per-org resolved/total
    network counts, read from the same ``meraki_network_filter_*`` gauges the
    inventory already emits (single source of truth).
    """

    is_active: bool
    include_names: list[str]
    include_ids: list[str]
    include_tags: list[str]
    exclude_names: list[str]
    exclude_ids: list[str]
    exclude_tags: list[str]
    # [{"org_id": ..., "total_networks": int, "resolved_networks": int}]
    per_org: list[dict[str, Any]]


@dataclass
class WebhookStatus:
    """Health of the webhook receiver pipeline (#317).

    Only populated when the webhook receiver is enabled. Counts come from the
    live ``WebhookHandler`` in-memory counters; ``events_by_type`` keys are the
    bounded ``alert_type`` values (never raw attacker input).
    """

    enabled: bool
    require_secret: bool
    events_received: int
    events_processed: int
    events_failed: int
    validation_failures: int
    last_event_time: float | None
    last_event_ago: str
    last_alert_type: str | None
    events_by_type: dict[str, int]


@dataclass
class SystemStatus:
    """Overall system status information."""

    version: str
    uptime: str
    readiness: dict[str, Any]
    org_health: list[OrgHealthStatus]


def _read_network_filter_gauges(
    registry: CollectorRegistry,
) -> list[dict[str, Any]]:
    """Read per-org network-filter counts from the emitted Prometheus gauges.

    Uses ``meraki_network_filter_networks`` (total discovered) and
    ``meraki_network_filter_resolved`` (included by the filter) so /status
    renders the same source of truth as the metrics, not a second computation.
    """
    total_name = NetworkMetricName.NETWORK_FILTER_NETWORKS.value
    resolved_name = NetworkMetricName.NETWORK_FILTER_RESOLVED.value
    totals: dict[str, int] = {}
    resolved: dict[str, int] = {}
    for family in registry.collect():
        if family.name == total_name:
            for sample in family.samples:
                org = sample.labels.get("org_id")
                if org is not None:
                    totals[org] = int(sample.value)
        elif family.name == resolved_name:
            for sample in family.samples:
                org = sample.labels.get("org_id")
                if org is not None:
                    resolved[org] = int(sample.value)
    per_org: list[dict[str, Any]] = []
    for org in sorted(set(totals) | set(resolved)):
        per_org.append({
            "org_id": org,
            "total_networks": totals.get(org, 0),
            "resolved_networks": resolved.get(org, totals.get(org, 0)),
        })
    return per_org


def build_network_filter_status(
    settings: Settings,
    registry: CollectorRegistry | None = None,
) -> NetworkFilterStatus:
    """Build the effective ``NetworkFilter`` status view (#311)."""
    nf = settings.network_filter
    reg = registry if registry is not None else REGISTRY
    return NetworkFilterStatus(
        is_active=nf.is_active,
        include_names=list(nf.include_names),
        include_ids=list(nf.include_ids),
        include_tags=list(nf.include_tags),
        exclude_names=list(nf.exclude_names),
        exclude_ids=list(nf.exclude_ids),
        exclude_tags=list(nf.exclude_tags),
        per_org=_read_network_filter_gauges(reg),
    )


def build_webhook_status(
    handler: WebhookHandler | None,
    settings: Settings,
    now: float | None = None,
) -> WebhookStatus | None:
    """Build the webhook-receiver status view (#317).

    Returns ``None`` when the webhook receiver is disabled (no handler), so the
    /status surface omits the section entirely rather than reporting zeros.
    """
    if handler is None or not settings.webhooks.enabled:
        return None
    stats = handler.get_status()
    return WebhookStatus(
        enabled=True,
        require_secret=settings.webhooks.require_secret,
        events_received=stats["events_received"],
        events_processed=stats["events_processed"],
        events_failed=stats["events_failed"],
        validation_failures=stats["validation_failures"],
        last_event_time=stats["last_event_time"],
        last_event_ago=_format_time_ago(stats["last_event_time"], now),
        last_alert_type=stats["last_alert_type"],
        events_by_type=stats["events_by_type"],
    )


def build_effective_config(settings: Settings) -> dict[str, Any]:
    """Build a redacted, JSON-safe view of the effective configuration (#312).

    Redaction relies on Pydantic's ``SecretStr`` masking: ``model_dump(mode="json")``
    renders every secret field (``meraki.api_key``, ``webhooks.shared_secret``,
    ``server.api_token``) as ``"**********"`` rather than its value, so this is
    the single canonical redaction path (aligns with SEC-07 / #564). Never build
    this dict from raw attribute access, which would bypass that masking.
    """
    return settings.model_dump(mode="json")


@dataclass
class StatusSnapshot:
    """Complete point-in-time snapshot of exporter health.

    Parameters
    ----------
    timestamp : str
        ISO-8601 formatted timestamp of when the snapshot was taken.
    system : SystemStatus
        Overall system status including version, uptime, and readiness.
    collectors : list[CollectorStatus]
        Status of each registered collector.
    api_health : ApiHealthStatus
        Health metrics for API interactions.
    data_freshness : DataFreshnessStatus
        Freshness information for collected metrics.

    """

    timestamp: str
    system: SystemStatus
    collectors: list[CollectorStatus]
    api_health: ApiHealthStatus
    data_freshness: DataFreshnessStatus
    network_filter: NetworkFilterStatus | None = None
    webhook: WebhookStatus | None = None
    # Adaptive scheduler diagnostics (#617): the manager's
    # get_scheduling_diagnostics()["scheduler"] dict (org shape, per-group
    # demand, configured+effective budget, solved intervals/stretch). ``None``
    # until the scheduler has resolved at least once. Additive key on the
    # /status JSON contract.
    scheduler: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the snapshot to a plain dictionary for JSON serialization."""
        return asdict(self)


class StatusService:
    """Aggregates exporter self-health into a StatusSnapshot."""

    def __init__(
        self,
        collector_manager: CollectorManager,
        expiration_manager: MetricExpirationManager,
        client: AsyncMerakiClient,
        settings: Settings,
        start_time: float,
        webhook_handler: WebhookHandler | None = None,
    ) -> None:
        """Initialise the status service.

        Parameters
        ----------
        collector_manager : CollectorManager
            Manager that holds collector state and health data.
        expiration_manager : MetricExpirationManager
            Tracks metric lifetimes and expiration stats.
        client : AsyncMerakiClient
            The Meraki API client (used for call counts).
        settings : Settings
            Application settings including update intervals.
        start_time : float
            Unix timestamp when the exporter was started.
        webhook_handler : WebhookHandler | None
            The live webhook receiver, when enabled, for surfacing its health
            on /status (#317). ``None`` when the receiver is disabled.

        """
        self._manager = collector_manager
        self._expiration = expiration_manager
        self._client = client
        self._settings = settings
        self._start_time = start_time
        self._webhook_handler = webhook_handler

    def get_snapshot(self) -> StatusSnapshot:
        """Build and return a point-in-time health snapshot of the exporter."""
        now = time.time()

        tier_intervals = {
            UpdateTier.FAST: self._settings.update_intervals.fast,
            UpdateTier.MEDIUM: self._settings.update_intervals.medium,
            UpdateTier.SLOW: self._settings.update_intervals.slow,
        }

        # Build collector statuses
        collectors: list[CollectorStatus] = []
        for tier, collector_list in self._manager.collectors.items():
            interval = tier_intervals[tier]
            for collector in collector_list:
                if not collector.is_active:
                    continue
                name = collector.__class__.__name__
                health = self._manager.collector_health.get(name, {})
                total_runs = health.get("total_runs", 0)
                total_successes = health.get("total_successes", 0)
                total_failures = health.get("total_failures", 0)
                success_rate = (total_successes / total_runs * 100) if total_runs > 0 else 0.0
                last_success_time = health.get("last_success_time")

                collectors.append(
                    CollectorStatus(
                        name=name,
                        tier=tier.value.upper(),
                        total_runs=total_runs,
                        total_successes=total_successes,
                        total_failures=total_failures,
                        success_rate=round(success_rate, 1),
                        failure_streak=health.get("failure_streak", 0),
                        last_success_time=last_success_time,
                        last_success_ago=_format_time_ago(last_success_time, now),
                        is_running=self._manager.is_collector_running(name),
                        staleness=_compute_staleness(last_success_time, interval, now),
                    )
                )

        # Build API health
        rate_limiter = self._manager.rate_limiter
        per_org: list[dict[str, Any]] = []
        if rate_limiter.enabled:
            for org_id, tokens in rate_limiter._tokens.items():
                per_org.append({"org_id": org_id, "tokens_remaining": round(tokens, 1)})

        # F-028/F-074: source real counters — total_calls from the Meraki request
        # counter (the old `_api_call_count` was never incremented) and
        # throttle_events from the rate limiter's throttled total (was hardcoded 0).
        api_health = ApiHealthStatus(
            total_calls=self._client.get_total_api_requests(),
            throttle_events=rate_limiter.get_total_throttled(),
            per_org_rate_limits=per_org,
            authenticated=self._client.get_auth_ok(),
        )

        # Build data freshness
        stats = self._expiration.get_stats()
        data_freshness = DataFreshnessStatus(
            total_tracked_metrics=stats["total_tracked"],
            by_collector=stats["by_collector"],
            ttl_multiplier=stats["ttl_multiplier"],
        )

        # Build org health
        org_health_list: list[OrgHealthStatus] = []
        org: OrgHealth
        for org in self._manager.org_health_tracker._orgs.values():
            remaining = max(0.0, org.backoff_until - now)
            org_health_list.append(
                OrgHealthStatus(
                    org_id=org.org_id,
                    org_name=org.org_name,
                    consecutive_failures=org.consecutive_failures,
                    in_backoff=remaining > 0,
                    backoff_remaining_seconds=round(remaining, 1),
                )
            )

        # Build uptime
        uptime_seconds = int(now - self._start_time)
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        if days > 0:
            uptime = f"{days}d {hours}h"
        elif hours > 0:
            uptime = f"{hours}h {minutes}m"
        else:
            uptime = f"{minutes}m"

        from ..__version__ import __version__

        system = SystemStatus(
            version=__version__,
            uptime=uptime,
            readiness=self._manager.get_readiness_status(),
            org_health=org_health_list,
        )

        # Effective NetworkFilter state (#311) and webhook receiver health (#317).
        network_filter = build_network_filter_status(self._settings)
        webhook = build_webhook_status(self._webhook_handler, self._settings, now)

        # Adaptive scheduler diagnostics (#617). The manager funnels the
        # EndpointScheduler snapshot under the "scheduler" key of its scheduling
        # diagnostics; it is absent (None) until the scheduler has resolved once
        # or in fixed-mode transition builds, so guard with .get().
        scheduler = self._manager.get_scheduling_diagnostics().get("scheduler")

        return StatusSnapshot(
            timestamp=datetime.now(UTC).isoformat(),
            system=system,
            collectors=collectors,
            api_health=api_health,
            data_freshness=data_freshness,
            network_filter=network_filter,
            webhook=webhook,
            scheduler=scheduler,
        )
