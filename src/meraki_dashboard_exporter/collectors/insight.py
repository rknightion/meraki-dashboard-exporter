"""Meraki Insight application-health collector (#613).

Meraki Insight is a license-gated WAN/application-health product layered on MX
appliances. This collector is **off by default** (``collectors.collect_insight``)
and degrades to a debug-level skip when the organization lacks an Insight
license — a non-Insight org returns HTTP 400/404 for the Insight endpoints,
which is treated as "not available" rather than a hard failure (mirrors
``organization_collectors/license.py``).

Two org-scoped scheduler groups drive it:

- ``INSIGHT_APPLICATIONS`` (priority 4, floor 3600s): one
  ``getOrganizationInsightApplications`` call per cycle listing the operator's
  monitored applications. Emits the monitored-application count plus a
  per-application ``_info`` join carrier (the only Insight series carrying the
  mutable ``name`` — #534 Option B).
- ``INSIGHT_APP_HEALTH`` (priority 4, floor 900s, gated behind
  ``collectors.insight_app_health_enabled``): a per-(network × application)
  fan-out of ``getNetworkInsightApplicationHealthByTime`` emitting id-only
  numeric health gauges (latency/loss/response-duration/throughput/clients).

⚠ Phase-6 LIVE VERIFICATION: this family is entirely spec-only pre-launch (the
homelab has neither an Insight license nor an MX). Confirm the healthByTime
bucket semantics (which bucket is "complete"), the exact null-field behaviour,
and the precise 400-vs-404 error shape for a non-Insight org against the live
API post-v1. The local Pydantic models use ``extra="allow"`` and Optional
fields to stay forward-compatible until then. ``wanGoodput``/``lanGoodput`` are
deliberately NOT emitted — the spec gives no unit and they cannot be
field-verified pre-launch.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict

from ..core.async_utils import ManagedTaskGroup
from ..core.collector import MetricCollector
from ..core.constants import InsightMetricName
from ..core.error_handling import (
    ErrorCategory,
    validate_response_format,
    with_error_handling,
)
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call
from ..core.logging_helpers import LogContext
from ..core.metrics import LabelName, create_labels
from ..core.registry import register_collector
from ..core.scheduler import EndpointGroup, EndpointGroupName

if TYPE_CHECKING:
    from prometheus_client import Gauge

logger = get_logger(__name__)

# Belt-and-braces hard cap on the number of monitored applications fanned out
# per organization (#613). The monitored-app set is operator-configured and
# small by product design, but a runaway config must never explode the
# per-(network × application) fan-out. Excess applications (sorted by
# applicationId) are dropped with a single WARNING per cycle.
_MAX_INSIGHT_APPS = 30

# Fixed window for the per-network application-health fetch: a trailing hour at
# 5-minute resolution, from which the newest complete bucket is taken.
_HEALTH_TIMESPAN_SECONDS = 3600
_HEALTH_RESOLUTION_SECONDS = 300


class InsightApplication(BaseModel):
    """One monitored application from ``getOrganizationInsightApplications`` (#613).

    ``applicationId`` is Optional so a malformed row (missing id) is skipped
    rather than aborting the whole parse; rows without an id cannot key a
    health series. ``extra="allow"`` keeps parsing forward-compatible with the
    (spec-only) response until Phase-6 live verification.
    """

    model_config = ConfigDict(extra="allow")

    applicationId: str | None = None
    name: str | None = None


class InsightHealthBucket(BaseModel):
    """One time bucket from ``getNetworkInsightApplicationHealthByTime`` (#613).

    Every metric field is Optional: the API may null out fields for a bucket
    with no traffic, and the newest bucket may be incomplete. ``goodput`` fields
    are modelled but deliberately never emitted (no documented unit).
    """

    model_config = ConfigDict(extra="allow")

    startTs: str | None = None
    endTs: str | None = None
    wanLatencyMs: float | None = None
    lanLatencyMs: float | None = None
    wanLossPercent: float | None = None
    lanLossPercent: float | None = None
    responseDuration: float | None = None  # milliseconds
    sent: float | None = None  # kilobytes/second
    recv: float | None = None  # kilobytes/second
    numClients: int | None = None
    # Modelled for completeness but intentionally NOT emitted (no unit; #613).
    wanGoodput: float | None = None
    lanGoodput: float | None = None

    @property
    def has_data(self) -> bool:
        """Whether the bucket carries at least one emittable value.

        Used to skip a trailing incomplete/empty bucket when selecting the
        newest complete bucket.
        """
        return any(
            v is not None
            for v in (
                self.wanLatencyMs,
                self.lanLatencyMs,
                self.wanLossPercent,
                self.lanLossPercent,
                self.responseDuration,
                self.sent,
                self.recv,
                self.numClients,
            )
        )


@register_collector
class InsightCollector(MetricCollector):
    """Collector for Meraki Insight application-health metrics (#613).

    Off by default; enabled via ``collectors.collect_insight``. The per-network
    application-health fan-out is additionally gated behind
    ``collectors.insight_app_health_enabled``.
    """

    # Scheduler endpoint groups (#617). Both carry ``enabled_fn`` (frozen in the
    # seam) keying off ``appliance_network_count`` — Insight is MX-based, so the
    # groups contribute zero demand and never run for an appliance-less org.
    endpoint_groups: ClassVar[tuple[EndpointGroup, ...]] = (
        EndpointGroup(
            name=EndpointGroupName.INSIGHT_APPLICATIONS,
            priority=4,
            floor_seconds=3600,
            cost_fn=lambda shape: 1.0,
            enabled_fn=lambda shape: shape.appliance_network_count > 0,
        ),
        EndpointGroup(
            name=EndpointGroupName.INSIGHT_APP_HEALTH,
            priority=4,
            floor_seconds=900,
            # Estimate: OrgShape has no monitored-app count, so approximate the
            # per-(network × application) fan-out as 10 apps per appliance
            # network (same estimate convention as MR_SSID_FIREWALL).
            cost_fn=lambda shape: 10.0 * shape.appliance_network_count,
            enabled_fn=lambda shape: shape.appliance_network_count > 0,
        ),
    )

    def get_endpoint_groups(self) -> tuple[EndpointGroup, ...]:
        """Return the active Insight groups given the current config.

        - ``()`` when ``collect_insight`` is off (nothing enters the solver).
        - Drop ``INSIGHT_APP_HEALTH`` when ``insight_app_health_enabled`` is off
          (only the cheap org-level applications call runs).

        Returns
        -------
        tuple[EndpointGroup, ...]
            The active endpoint groups.

        """
        if not self.settings.collectors.collect_insight:
            return ()
        if not self.settings.collectors.insight_app_health_enabled:
            return tuple(
                g
                for g in type(self).endpoint_groups
                if g.name != EndpointGroupName.INSIGHT_APP_HEALTH
            )
        return type(self).endpoint_groups

    @property
    def is_active(self) -> bool:
        """Whether Insight collection is enabled (``collect_insight``)."""
        return bool(self.settings.collectors.collect_insight)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the Insight collector.

        Parameters
        ----------
        *args : Any
            Positional arguments forwarded to :class:`MetricCollector`.
        **kwargs : Any
            Keyword arguments forwarded to :class:`MetricCollector`.

        """
        super().__init__(*args, **kwargs)
        # Per-org cache of the selected (post-cap) monitored applications so a
        # heartbeat where only INSIGHT_APP_HEALTH is due (its 900s floor fires
        # more often than the 3600s applications floor) can fan out without a
        # redundant getOrganizationInsightApplications call.
        self._app_cache: dict[str, list[InsightApplication]] = {}

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for Insight application health."""
        self._applications = self._create_gauge(
            InsightMetricName.INSIGHT_APPLICATIONS,
            "Number of applications in the organization's Meraki Insight monitored set",
            labelnames=[LabelName.ORG_ID],
        )
        # id -> name join carrier (#534 Option B): the ONLY Insight series
        # carrying the mutable application name. Numeric health series are
        # id-only and join via `on(application_id) group_left(name)`.
        self._application_info = self._create_gauge(
            InsightMetricName.INSIGHT_APPLICATION_INFO,
            "Meraki Insight application info (application_id -> name); value is always 1",
            labelnames=[LabelName.ORG_ID, LabelName.APPLICATION_ID, LabelName.NAME],
        )
        self._wan_latency = self._create_gauge(
            InsightMetricName.INSIGHT_APPLICATION_WAN_LATENCY_SECONDS,
            "Meraki Insight application WAN latency in seconds (most recent complete "
            "5-minute bucket over the trailing hour)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID, LabelName.APPLICATION_ID],
        )
        self._lan_latency = self._create_gauge(
            InsightMetricName.INSIGHT_APPLICATION_LAN_LATENCY_SECONDS,
            "Meraki Insight application LAN latency in seconds (most recent complete "
            "5-minute bucket over the trailing hour)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID, LabelName.APPLICATION_ID],
        )
        self._wan_loss = self._create_gauge(
            InsightMetricName.INSIGHT_APPLICATION_WAN_LOSS_PERCENT,
            "Meraki Insight application WAN loss percent (most recent complete "
            "5-minute bucket over the trailing hour)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID, LabelName.APPLICATION_ID],
        )
        self._lan_loss = self._create_gauge(
            InsightMetricName.INSIGHT_APPLICATION_LAN_LOSS_PERCENT,
            "Meraki Insight application LAN loss percent (most recent complete "
            "5-minute bucket over the trailing hour)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID, LabelName.APPLICATION_ID],
        )
        self._response_duration = self._create_gauge(
            InsightMetricName.INSIGHT_APPLICATION_RESPONSE_DURATION_SECONDS,
            "Meraki Insight application response duration in seconds (most recent "
            "complete 5-minute bucket over the trailing hour)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID, LabelName.APPLICATION_ID],
        )
        self._sent_bytes_per_second = self._create_gauge(
            InsightMetricName.INSIGHT_APPLICATION_SENT_BYTES_PER_SECOND,
            "Meraki Insight application bytes sent per second (most recent complete "
            "5-minute bucket over the trailing hour)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID, LabelName.APPLICATION_ID],
        )
        self._recv_bytes_per_second = self._create_gauge(
            InsightMetricName.INSIGHT_APPLICATION_RECV_BYTES_PER_SECOND,
            "Meraki Insight application bytes received per second (most recent complete "
            "5-minute bucket over the trailing hour)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID, LabelName.APPLICATION_ID],
        )
        self._clients_count = self._create_gauge(
            InsightMetricName.INSIGHT_APPLICATION_CLIENTS_COUNT,
            "Meraki Insight application client count over the most recent complete "
            "5-minute bucket (windowed count, not a monotonic counter)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID, LabelName.APPLICATION_ID],
        )

    async def _collect_impl(self) -> None:
        """Collect Insight application-health metrics across all organizations."""
        if not self.settings.collectors.collect_insight:
            logger.debug("Insight collection disabled (collect_insight=False); skipping")
            return

        if not self.inventory:
            raise RuntimeError(
                "Inventory service not configured for InsightCollector. This is a "
                "programming error - collectors must be initialized with inventory."
            )

        apps_due = self._should_run_group(EndpointGroupName.INSIGHT_APPLICATIONS)
        health_due = self.settings.collectors.insight_app_health_enabled and self._should_run_group(
            EndpointGroupName.INSIGHT_APP_HEALTH
        )
        if not apps_due and not health_due:
            logger.debug("No Insight groups due this heartbeat; skipping")
            return

        organizations = await self.inventory.get_organizations()
        if not organizations:
            logger.debug("No organizations found for Insight collection")
            return

        for org in organizations:
            org_id = org["id"]
            org_name = org.get("name", org_id)
            with LogContext(org_id=org_id, org_name=org_name):
                await self._collect_org(org_id, org_name, apps_due=apps_due, health_due=health_due)

        # Advance the scheduler's last-ran clock for each group that was due.
        if apps_due:
            self._mark_group_ran(EndpointGroupName.INSIGHT_APPLICATIONS)
        if health_due:
            self._mark_group_ran(EndpointGroupName.INSIGHT_APP_HEALTH)

    @with_error_handling(
        operation="Collect Insight applications",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_org(
        self,
        org_id: str,
        org_name: str,
        *,
        apps_due: bool,
        health_due: bool,
    ) -> None:
        """Collect Insight metrics for one organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        apps_due : bool
            Whether the applications group is due this heartbeat.
        health_due : bool
            Whether the per-network application-health group is due (and
            enabled) this heartbeat.

        """
        # (Re)fetch the monitored-application inventory when the applications
        # group is due, or when the cache is cold (needed to fan out health).
        if apps_due or org_id not in self._app_cache:
            raw_apps = await self._fetch_applications(org_id)
            if raw_apps is None:
                logger.debug(
                    "Insight applications unavailable for organization; skipping",
                    org_id=org_id,
                )
                return
            applications = [InsightApplication.model_validate(a) for a in raw_apps]
            selected = self._select_applications(applications, org_id)
            self._app_cache[org_id] = selected
            self._emit_application_inventory(org_id, applications, selected)

        selected = self._app_cache.get(org_id, [])
        if health_due and selected:
            await self._collect_application_health(org_id, org_name, selected)

    def _select_applications(
        self, applications: list[InsightApplication], org_id: str
    ) -> list[InsightApplication]:
        """Sort by applicationId, drop id-less rows, and cap at ``_MAX_INSIGHT_APPS``.

        Parameters
        ----------
        applications : list[InsightApplication]
            All parsed monitored applications.
        org_id : str
            Organization ID (for the over-cap warning).

        Returns
        -------
        list[InsightApplication]
            The selected applications (health/info are emitted for these only).

        """
        with_id = sorted(
            (a for a in applications if a.applicationId),
            key=lambda a: cast(str, a.applicationId),
        )
        if len(with_id) > _MAX_INSIGHT_APPS:
            logger.warning(
                "Insight monitored-application count exceeds cap; dropping excess",
                org_id=org_id,
                total=len(with_id),
                cap=_MAX_INSIGHT_APPS,
                dropped=len(with_id) - _MAX_INSIGHT_APPS,
            )
        return with_id[:_MAX_INSIGHT_APPS]

    def _emit_application_inventory(
        self,
        org_id: str,
        applications: list[InsightApplication],
        selected: list[InsightApplication],
    ) -> None:
        """Emit the monitored-app count and per-application info join carrier.

        Parameters
        ----------
        org_id : str
            Organization ID.
        applications : list[InsightApplication]
            All monitored applications (the count reflects this true total).
        selected : list[InsightApplication]
            The post-cap subset for which health series (and thus info series)
            are emitted.

        """
        ttl = self._group_ttl_seconds(EndpointGroupName.INSIGHT_APPLICATIONS)
        self._set_metric(
            self._applications,
            create_labels(org_id=org_id),
            float(len(applications)),
            InsightMetricName.INSIGHT_APPLICATIONS.value,
            ttl_seconds=ttl,
        )
        for app in selected:
            self._set_metric(
                self._application_info,
                create_labels(
                    org_id=org_id,
                    application_id=app.applicationId,
                    name=app.name,
                ),
                1,
                InsightMetricName.INSIGHT_APPLICATION_INFO.value,
                ttl_seconds=ttl,
            )

    async def _collect_application_health(
        self,
        org_id: str,
        org_name: str,
        selected: list[InsightApplication],
    ) -> None:
        """Fan out per-(network × application) health collection.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        selected : list[InsightApplication]
            The (post-cap) monitored applications to query per network.

        """
        assert self.inventory is not None  # guaranteed by _collect_impl
        networks = await self.inventory.get_networks(org_id)
        if not networks:
            logger.debug("No networks for Insight application-health fan-out", org_id=org_id)
            return

        ttl = self._group_ttl_seconds(EndpointGroupName.INSIGHT_APP_HEALTH)
        async with ManagedTaskGroup(
            name="insight_app_health",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for network in networks:
                network_id = network["id"]
                for app in selected:
                    await group.create_task(
                        self._collect_app_health(org_id, network_id, app, ttl),
                        name=f"{network_id}:{app.applicationId}",
                    )

    @with_error_handling(
        operation="Collect Insight application health",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_app_health(
        self,
        org_id: str,
        network_id: str,
        app: InsightApplication,
        ttl: float | None,
    ) -> None:
        """Fetch and emit health for one (network, application) pair.

        Parameters
        ----------
        org_id : str
            Organization ID.
        network_id : str
            Network ID.
        app : InsightApplication
            The monitored application.
        ttl : float | None
            Per-series TTL for the INSIGHT_APP_HEALTH group.

        """
        application_id = cast(str, app.applicationId)
        raw = await self._fetch_application_health(network_id, application_id)
        if raw is None:
            return
        buckets = [InsightHealthBucket.model_validate(b) for b in raw]
        bucket = self._newest_complete_bucket(buckets)
        if bucket is None:
            logger.debug(
                "No complete Insight health bucket returned",
                network_id=network_id,
                application_id=application_id,
            )
            return
        self._emit_health(org_id, network_id, application_id, bucket, ttl)

    @staticmethod
    def _newest_complete_bucket(
        buckets: list[InsightHealthBucket],
    ) -> InsightHealthBucket | None:
        """Return the newest bucket carrying data, or ``None``.

        Buckets are returned chronologically; the trailing bucket may be an
        incomplete/empty in-progress window, so the newest bucket with at least
        one emittable value is selected.

        Parameters
        ----------
        buckets : list[InsightHealthBucket]
            The parsed health buckets over the trailing hour.

        Returns
        -------
        InsightHealthBucket | None
            The newest complete bucket, or ``None`` when none carry data.

        """
        for bucket in reversed(buckets):
            if bucket.has_data:
                return bucket
        return None

    def _emit_health(
        self,
        org_id: str,
        network_id: str,
        application_id: str,
        bucket: InsightHealthBucket,
        ttl: float | None,
    ) -> None:
        """Emit the id-only numeric health series for one bucket.

        Parameters
        ----------
        org_id : str
            Organization ID.
        network_id : str
            Network ID.
        application_id : str
            Monitored-application ID.
        bucket : InsightHealthBucket
            The selected complete bucket.
        ttl : float | None
            Per-series TTL for the INSIGHT_APP_HEALTH group.

        """
        labels = create_labels(
            org_id=org_id,
            network_id=network_id,
            application_id=application_id,
        )

        def _emit(metric: Gauge, name: str, value: float | None) -> None:
            if value is None:
                return
            self._set_metric(metric, labels, value, name, ttl_seconds=ttl)

        # Latency/response-duration: API milliseconds -> seconds.
        _emit(
            self._wan_latency,
            InsightMetricName.INSIGHT_APPLICATION_WAN_LATENCY_SECONDS.value,
            None if bucket.wanLatencyMs is None else bucket.wanLatencyMs / 1000,
        )
        _emit(
            self._lan_latency,
            InsightMetricName.INSIGHT_APPLICATION_LAN_LATENCY_SECONDS.value,
            None if bucket.lanLatencyMs is None else bucket.lanLatencyMs / 1000,
        )
        _emit(
            self._response_duration,
            InsightMetricName.INSIGHT_APPLICATION_RESPONSE_DURATION_SECONDS.value,
            None if bucket.responseDuration is None else bucket.responseDuration / 1000,
        )
        # Loss: percent, as-is.
        _emit(
            self._wan_loss,
            InsightMetricName.INSIGHT_APPLICATION_WAN_LOSS_PERCENT.value,
            bucket.wanLossPercent,
        )
        _emit(
            self._lan_loss,
            InsightMetricName.INSIGHT_APPLICATION_LAN_LOSS_PERCENT.value,
            bucket.lanLossPercent,
        )
        # Throughput: API decimal kilobytes/second -> bytes/second (×1000).
        _emit(
            self._sent_bytes_per_second,
            InsightMetricName.INSIGHT_APPLICATION_SENT_BYTES_PER_SECOND.value,
            None if bucket.sent is None else bucket.sent * 1000,
        )
        _emit(
            self._recv_bytes_per_second,
            InsightMetricName.INSIGHT_APPLICATION_RECV_BYTES_PER_SECOND.value,
            None if bucket.recv is None else bucket.recv * 1000,
        )
        # Windowed client count.
        _emit(
            self._clients_count,
            InsightMetricName.INSIGHT_APPLICATION_CLIENTS_COUNT.value,
            None if bucket.numClients is None else float(bucket.numClients),
        )

    @log_api_call("getOrganizationInsightApplications")
    async def _fetch_applications(self, org_id: str) -> list[dict[str, Any]] | None:
        """Fetch the monitored-application inventory for an organization.

        Returns ``None`` (debug-skip) when Insight is unavailable for this org
        (HTTP 400/404 — license-gated). Other errors propagate to the
        ``@with_error_handling`` wrapper on the caller.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]] | None
            The application rows, or ``None`` when unavailable.

        """
        try:
            response = await asyncio.to_thread(
                self.api.insight.getOrganizationInsightApplications,
                org_id,
            )
        except Exception as e:
            if self._is_license_absent(e):
                logger.debug(
                    "Insight not available for organization (license-gated); skipping",
                    org_id=org_id,
                )
                return None
            raise
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationInsightApplications",
            ),
        )

    @log_api_call("getNetworkInsightApplicationHealthByTime")
    async def _fetch_application_health(
        self, network_id: str, application_id: str
    ) -> list[dict[str, Any]] | None:
        """Fetch application-health buckets for one (network, application) pair.

        Returns ``None`` (debug-skip) when Insight is unavailable (HTTP
        400/404). Other errors propagate to the caller's ``@with_error_handling``.

        Parameters
        ----------
        network_id : str
            Network ID.
        application_id : str
            Monitored-application ID.

        Returns
        -------
        list[dict[str, Any]] | None
            The health buckets, or ``None`` when unavailable.

        """
        try:
            response = await asyncio.to_thread(
                self.api.insight.getNetworkInsightApplicationHealthByTime,
                network_id,
                application_id,
                timespan=_HEALTH_TIMESPAN_SECONDS,
                resolution=_HEALTH_RESOLUTION_SECONDS,
            )
        except Exception as e:
            if self._is_license_absent(e):
                logger.debug(
                    "Insight application health unavailable (license-gated); skipping",
                    network_id=network_id,
                    application_id=application_id,
                )
                return None
            raise
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getNetworkInsightApplicationHealthByTime",
            ),
        )

    @staticmethod
    def _is_license_absent(error: Exception) -> bool:
        """Whether an error indicates Insight is unavailable for the org (400/404).

        Prefers the structured HTTP status (``meraki.APIError.status``) and
        falls back to a substring check for non-APIError exceptions.

        Parameters
        ----------
        error : Exception
            The raised exception.

        Returns
        -------
        bool
            True when the error is a 400/404 "not available" response.

        """
        status = getattr(error, "status", None)
        if status is not None:
            return status in {400, 404}
        msg = str(error)
        return "400" in msg or "404" in msg
