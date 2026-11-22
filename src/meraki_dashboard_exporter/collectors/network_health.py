"""Medium-tier network health metric collector."""

from __future__ import annotations

import asyncio
import functools
import math
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from time import monotonic
from typing import TYPE_CHECKING, Any, ClassVar

from ..core.async_utils import ManagedTaskGroup
from ..core.batch_processing import process_in_batches_with_errors
from ..core.collector import MetricCollector
from ..core.constants import NetworkHealthMetricName, NetworkMetricName, ProductType
from ..core.error_handling import (
    ErrorCategory,
    NothingCollectedError,
    categorize_error,
    with_error_handling,
)
from ..core.fanout_cursor import (
    FanoutCursor,
    failure_retry_spacing,
    per_attempt_call_budget,
    sweep_ttl_seconds,
)
from ..core.logging import get_logger
from ..core.logging_decorators import log_batch_operation
from ..core.logging_helpers import log_metric_collection_summary
from ..core.metrics import LabelName
from ..core.otel_tracing import trace_method
from ..core.registry import register_collector
from ..core.scheduler import EndpointGroup, EndpointGroupName, pages
from .network_health_collectors.air_marshal import AirMarshalCollector
from .network_health_collectors.bluetooth import BluetoothCollector
from .network_health_collectors.connection_stats import ConnectionStatsCollector
from .network_health_collectors.data_rates import DataRatesCollector
from .network_health_collectors.latency_stats import LatencyStatsCollector
from .network_health_collectors.mesh import MeshCollector
from .network_health_collectors.rf_health import RFHealthCollector
from .network_health_collectors.ssid_performance import SSIDPerformanceCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager
    from ..core.org_health import OrgHealthTracker
    from ..services.inventory import OrganizationInventory

from ..core.org_health import SOURCE_NETWORK_HEALTH

logger = get_logger(__name__)


# Latency fetches both device and client aggregates; every other bundle group
# makes one logical endpoint call. Org-wide channel utilization is separate.
_LATENCY_CALLS = 2
_BUNDLE_CALL_COSTS = {
    EndpointGroupName.NH_CONNECTION_STATS: 1,
    EndpointGroupName.NH_DATA_RATES: 1,
    EndpointGroupName.NH_BLUETOOTH: 1,
    EndpointGroupName.NH_FAILED_CONNECTIONS: 1,
    EndpointGroupName.NH_LATENCY_STATS: _LATENCY_CALLS,
    EndpointGroupName.NH_AIR_MARSHAL: 1,
    EndpointGroupName.NH_MESH: 1,
}


@register_collector
class NetworkHealthCollector(MetricCollector):
    """Collector for medium-moving network health metrics."""

    # Endpoint-group declarations for the adaptive scheduler (#617 §2). All
    # network-health groups run on the MEDIUM heartbeat at priority 3
    # (perf/health). #541 folds the windowed floors (connection-stats 1800s;
    # failed-connections / latency / air-marshal 3600s). Channel-utilization is
    # the org-wide #271 rewrite, costed as two paginated org endpoints.
    #
    # #630 (live-verified 2026-07-03, org <org-id>): each windowed group's floor
    # equals the timespan its fetcher passes (connection-stats 1800; failed-conn
    # / latency / air-marshal 3600), so successive polls read non-overlapping
    # windows — polling faster would just re-aggregate an overlapping window. The
    # spec caps these timespans at 7 days (air-marshal 31 days), so the floors
    # are well within legal range.
    # enabled_fn: _collect_org_network_health returns before consulting any gate
    # when the org has no wireless networks, so without it every group reads
    # "due now" forever and spins the collector loop (#789).
    endpoint_groups: ClassVar[tuple[EndpointGroup, ...]] = (
        EndpointGroup(
            name=EndpointGroupName.NH_CHANNEL_UTILIZATION,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda shape: 2 * pages(shape.ap_count, 1000),
            enabled_fn=lambda s: s.wireless_network_count > 0,
        ),
        EndpointGroup(
            name=EndpointGroupName.NH_CONNECTION_STATS,
            priority=3,
            floor_seconds=1800,
            self_paced=True,
            cost_fn=lambda shape: float(shape.wireless_network_count),
            enabled_fn=lambda s: s.wireless_network_count > 0,
        ),
        EndpointGroup(
            name=EndpointGroupName.NH_DATA_RATES,
            priority=3,
            floor_seconds=300,
            self_paced=True,
            cost_fn=lambda shape: float(shape.wireless_network_count),
            enabled_fn=lambda s: s.wireless_network_count > 0,
        ),
        EndpointGroup(
            name=EndpointGroupName.NH_BLUETOOTH,
            priority=3,
            floor_seconds=300,
            self_paced=True,
            cost_fn=lambda shape: float(shape.wireless_network_count),
            enabled_fn=lambda s: s.wireless_network_count > 0,
        ),
        EndpointGroup(
            name=EndpointGroupName.NH_FAILED_CONNECTIONS,
            priority=3,
            floor_seconds=3600,
            self_paced=True,
            cost_fn=lambda shape: float(shape.wireless_network_count),
            enabled_fn=lambda s: s.wireless_network_count > 0,
        ),
        EndpointGroup(
            name=EndpointGroupName.NH_LATENCY_STATS,
            priority=3,
            floor_seconds=3600,
            self_paced=True,
            cost_fn=lambda shape: 2.0 * shape.wireless_network_count,
            enabled_fn=lambda s: s.wireless_network_count > 0,
        ),
        EndpointGroup(
            name=EndpointGroupName.NH_AIR_MARSHAL,
            priority=3,
            floor_seconds=3600,
            self_paced=True,
            cost_fn=lambda shape: float(shape.wireless_network_count),
            enabled_fn=lambda s: s.wireless_network_count > 0,
        ),
        # Wireless mesh link health (#307, Phase 4/#618). Repeater topology
        # changes rarely; floored the same as the other 1h-windowed groups.
        EndpointGroup(
            name=EndpointGroupName.NH_MESH,
            priority=3,
            floor_seconds=3600,
            self_paced=True,
            cost_fn=lambda shape: float(shape.wireless_network_count),
            enabled_fn=lambda s: s.wireless_network_count > 0,
        ),
    )

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
        inventory: OrganizationInventory | None = None,
        expiration_manager: MetricExpirationManager | None = None,
        rate_limiter: Any | None = None,
        scheduler: Any | None = None,
        data_log_emitter: Any | None = None,
        org_health_tracker: OrgHealthTracker | None = None,
    ) -> None:
        """Initialize network health collector with sub-collectors."""
        super().__init__(
            api,
            settings,
            registry,
            inventory,
            expiration_manager,
            rate_limiter,
            scheduler=scheduler,
            data_log_emitter=data_log_emitter,
        )

        # Shared per-org health tracker (F-169 / #547): when present, per-org
        # collection is skipped for organizations currently in backoff, AND this
        # collector reports its own per-org verdict into the tracker under the
        # SOURCE_NETWORK_HEALTH failure domain so network-endpoint failures engage
        # backoff even when the organization collector is healthy or disabled.
        self.org_health_tracker = org_health_tracker
        self._bundle_cursors: dict[str, dict[EndpointGroupName, FanoutCursor]] = {}
        # Parallel org workers and their network tasks inherit their own sweep TTLs.
        self._bundle_ttls: ContextVar[dict[EndpointGroupName, float | None] | None] = ContextVar(
            "network_health_bundle_ttls", default=None
        )

        # Initialize sub-collectors
        self.rf_health_collector = RFHealthCollector(self)
        self.connection_stats_collector = ConnectionStatsCollector(self)
        self.data_rates_collector = DataRatesCollector(self)
        self.bluetooth_collector = BluetoothCollector(self)
        self.ssid_performance_collector = SSIDPerformanceCollector(self)
        self.latency_stats_collector = LatencyStatsCollector(self)
        self.air_marshal_collector = AirMarshalCollector(self)
        self.mesh_collector = MeshCollector(self)

    def _initialize_metrics(self) -> None:
        """Initialize network health metrics."""
        # RF channel utilization metrics per AP
        self._ap_utilization_2_4ghz = self._create_gauge(
            NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_2_4GHZ_PERCENT,
            "2.4GHz channel utilization percentage per AP, 10-min bucket",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.UTILIZATION_TYPE,
            ],
        )

        self._ap_utilization_5ghz = self._create_gauge(
            NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_5GHZ_PERCENT,
            "5GHz channel utilization percentage per AP, 10-min bucket",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.UTILIZATION_TYPE,
            ],
        )

        # 6GHz (WiFi-6E). Added #630: emitted for band == "6" rows instead of
        # dropping them (no 6E hardware in the test orgs, but the byBand band
        # string is the numeric GHz value, live-verified 2026-07-03).
        self._ap_utilization_6ghz = self._create_gauge(
            NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_6GHZ_PERCENT,
            "6GHz channel utilization percentage per AP, 10-min bucket",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.UTILIZATION_TYPE,
            ],
        )

        # Network-wide average utilization
        self._network_utilization_2_4ghz = self._create_gauge(
            NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_2_4GHZ_PERCENT,
            "Network-wide average 2.4GHz channel utilization percentage, 10-min bucket",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.UTILIZATION_TYPE,
            ],
        )

        self._network_utilization_5ghz = self._create_gauge(
            NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_5GHZ_PERCENT,
            "Network-wide average 5GHz channel utilization percentage, 10-min bucket",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.UTILIZATION_TYPE,
            ],
        )

        # 6GHz (WiFi-6E) network-wide average, paired with the per-AP gauge above (#630).
        self._network_utilization_6ghz = self._create_gauge(
            NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_6GHZ_PERCENT,
            "Network-wide average 6GHz channel utilization percentage, 10-min bucket",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.UTILIZATION_TYPE,
            ],
        )

        # Network-wide wireless connection statistics
        self._network_connection_stats = self._create_gauge(
            NetworkMetricName.NETWORK_WIRELESS_CONNECTION_STATS_COUNT,
            "Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.STAT_TYPE,
            ],
        )

        # Network-wide wireless data rate metrics
        self._network_wireless_download_kbps = self._create_gauge(
            NetworkHealthMetricName.NETWORK_WIRELESS_DOWNLOAD_BYTES_PER_SECOND,
            # The Meraki API reports this field (downloadKbps) in kilobytes-per-second,
            # not kilobits, per the OpenAPI spec (F-065). Value is converted x1000 to
            # bytes/second at collection time (#531 D5/APIDEV-03).
            "Network-wide wireless download bandwidth in bytes per second, 5-min bucket",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
            ],
        )

        self._network_wireless_upload_kbps = self._create_gauge(
            NetworkHealthMetricName.NETWORK_WIRELESS_UPLOAD_BYTES_PER_SECOND,
            # The Meraki API reports this field (uploadKbps) in kilobytes-per-second,
            # not kilobits, per the OpenAPI spec (F-065). Value is converted x1000 to
            # bytes/second at collection time (#531 D5/APIDEV-03).
            "Network-wide wireless upload bandwidth in bytes per second, 5-min bucket",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
            ],
        )

        # Bluetooth clients detected by MR devices
        self._network_bluetooth_clients_total = self._create_gauge(
            NetworkHealthMetricName.NETWORK_BLUETOOTH_CLIENTS_COUNT,
            "Number of Bluetooth clients detected by MR devices in the last 5 minutes",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
            ],
        )

        # Per-SSID failed connections (Phase 4.4)
        self._ssid_failed_connections = self._create_gauge(
            NetworkHealthMetricName.MR_SSID_FAILED_CONNECTIONS_COUNT,
            "Failed wireless connections by SSID and failure step over the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SSID,
                LabelName.FAILURE_STEP,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect network health metrics with parallel organization processing.

        Organizations are processed in parallel with bounded concurrency
        to significantly improve performance for multi-org deployments.

        Raises
        ------
        NothingCollectedError
            If organizations were present but every org-scope worker failed
            or was skipped for backoff (#509 / RES-01) — a failure signal for
            the manager instead of a spurious success.

        """
        start_time = asyncio.get_event_loop().time()
        metrics_collected = 0
        organizations_processed = 0
        api_calls_made = 0

        # Get organizations (raises on total failure; no blanket swallow).
        organizations = await self._fetch_organizations()
        if organizations is not None:
            for org_id in self._bundle_cursors.keys() - {org["id"] for org in organizations}:
                del self._bundle_cursors[org_id]
        if not organizations:
            logger.warning("No organizations found for network health collection")
            return
        api_calls_made += 1

        logger.info(
            "Starting parallel organization processing",
            org_count=len(organizations),
            concurrency_limit=self.settings.api.concurrency_limit,
        )

        # Process organizations in parallel with bounded concurrency. Backoff
        # checks happen here (before task creation) rather than inside the
        # worker so an all-in-backoff cycle can't masquerade as success (#509).
        skipped_backoff = 0
        async with ManagedTaskGroup(
            name="network_health_collector_orgs",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for org in organizations:
                org_id = org["id"]
                org_name = org.get("name", org_id)
                if (
                    self.org_health_tracker is not None
                    and not self.org_health_tracker.should_collect(
                        org_id, source=SOURCE_NETWORK_HEALTH
                    )
                ):
                    skipped_backoff += 1
                    logger.debug(
                        "Skipping network health collection for organization in backoff",
                        org_id=org_id,
                        org_name=org_name,
                    )
                    continue
                await group.create_task(
                    self._collect_org_network_health(org_id, org_name),
                    name=f"org_{org_id}",
                )
                organizations_processed += 1

        attempted = len(organizations) - skipped_backoff
        if (
            organizations
            and group.succeeded_count == 0
            and (group.failed_count > 0 or attempted == 0)
        ):
            raise NothingCollectedError(
                self.__class__.__name__,
                attempted=attempted,
                failed=group.failed_count,
                skipped_backoff=skipped_backoff,
            )

        # Approximate API calls (actual count may vary)
        api_calls_made += organizations_processed * 5

        # Log collection summary
        log_metric_collection_summary(
            "NetworkHealthCollector",
            metrics_collected=metrics_collected,
            duration_seconds=asyncio.get_event_loop().time() - start_time,
            organizations_processed=organizations_processed,
            api_calls_made=api_calls_made,
        )

    @with_error_handling(
        operation="Fetch organizations",
        continue_on_error=False,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_organizations(self) -> list[dict[str, Any]]:
        """Fetch organizations for network health collection using inventory cache.

        Returns
        -------
        list[dict[str, Any]] | None
            List of organizations or None on error.

        Raises
        ------
        RuntimeError
            If inventory service is not configured.

        """
        if not self.inventory:
            raise RuntimeError(
                "Inventory service not configured for NetworkHealthCollector. "
                "This is a programming error - collectors must be initialized with inventory service."
            )

        # No _track_api_call here: inventory.get_organizations() is served from the
        # inventory cache (the cache accounts for its own real upstream calls);
        # counting it here inflated the exporter's API-budget telemetry on cache hits.
        return await self.inventory.get_organizations()

    @trace_method("process.organization")
    @log_batch_operation("collect network health", batch_size=None)
    @with_error_handling(
        operation="Collect organization network health",
        apply_deadline=False,
        continue_on_error=False,
    )
    async def _collect_org_network_health(self, org_id: str, org_name: str | None = None) -> None:
        """Collect network health metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str | None
            Organization name.

        Raises
        ------
        Exception
            If ``_fetch_networks_for_health`` fails (org failed this cycle).
            Per-network bundle failures are isolated by
            ``process_in_batches_with_errors`` and do NOT raise here (org
            still counts as succeeded) — #509 frozen semantics.

        """
        # #547: report this org's network-health verdict into the shared tracker.
        # The verdict mirrors the coordinator's raise/return accounting exactly --
        # the worker "fails" only when the network fetch raises; per-network bundle
        # failures are isolated by process_in_batches_with_errors and are a
        # success for this domain. Recorded in a finally so exactly one verdict is
        # written per org per cycle, on every path, before the raise propagates.
        nh_failed = False
        failure_category: ErrorCategory | None = None
        try:
            # Get all networks. A failure here (raised through inventory) means
            # this org's worker fails; no blanket swallow.
            networks = await self._fetch_networks_for_health(org_id)

            # Add org info to each network
            for network in networks:
                network["orgId"] = org_id
                network["orgName"] = org_name or org_id

            wireless_networks = [
                network
                for network in networks
                if ProductType.WIRELESS in network.get("productTypes", [])
            ]
            if not wireless_networks:
                self._bundle_cursors.pop(org_id, None)
                return

            # Channel utilization is an org-wide fetch (#271) gated on its own
            # group and executed once per cycle (not per network). The two org
            # endpoints return every wireless device/network in the org in one
            # paginated pass each, so per-network fan-out here would be wasteful.
            if self._should_run_group(EndpointGroupName.NH_CHANNEL_UTILIZATION):
                channel_util_ok = await self.rf_health_collector.collect_org(
                    org_id, org_name or org_id, wireless_networks
                )
                # Mark ran only if the org-wide fetch achieved >=1 successful
                # fetch this cycle (#629). Total failure leaves the gate open so
                # the next cycle retries instead of waiting out the interval.
                if channel_util_ok:
                    self._mark_group_ran(EndpointGroupName.NH_CHANNEL_UTILIZATION)

            await self._collect_network_health_fanout(org_id, org_name or org_id, wireless_networks)
        except Exception as exc:
            nh_failed = True
            failure_category = categorize_error(exc)
            raise
        finally:
            self._record_org_health_verdict(
                org_id,
                org_name or org_id,
                success=not nh_failed,
                category=failure_category,
            )

    def _record_org_health_verdict(
        self,
        org_id: str,
        org_name: str,
        *,
        success: bool,
        category: ErrorCategory | None = None,
    ) -> None:
        """Report this org's network-health verdict into the shared tracker (#547).

        No-op when no tracker is wired. Runs synchronously (no await) so
        concurrent per-org workers never interleave a read-modify-write on the
        tracker's per-source counters.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        success : bool
            True to record a network-health success for this org, False a failure.
        category : ErrorCategory | None
            Classification of the failure, when available.

        """
        if self.org_health_tracker is None:
            return
        if success:
            self.org_health_tracker.record_success(org_id, org_name, source=SOURCE_NETWORK_HEALTH)
        else:
            self.org_health_tracker.record_failure(
                org_id, org_name, source=SOURCE_NETWORK_HEALTH, category=category
            )

    def _bundle_group_enabled(self, group: EndpointGroupName) -> bool:
        """Honor the solved profile and shedding, without admitting a group-level attempt."""
        return self.scheduler is None or self.scheduler.is_enabled(group)

    def _bundle_cadence_seconds(self) -> float:
        """Upper bound on the wake interval set by channel utilization and the resolve cap."""
        cap = float(self.settings.scheduler.resolve_interval_seconds)
        channel_group = EndpointGroupName.NH_CHANNEL_UTILIZATION
        if self._bundle_group_enabled(channel_group):
            return min(cap, float(self._group_interval(channel_group)))
        return cap

    def _group_ttl_seconds(self, group: EndpointGroupName) -> float | None:
        """Use the sweep TTL only for writes inside the requesting org's fan-out."""
        ttls = self._bundle_ttls.get()
        if ttls is not None and group in ttls:
            return ttls[group]
        return super()._group_ttl_seconds(group)

    async def _collect_network_health_fanout(
        self, org_id: str, org_name: str, networks: list[dict[str, Any]]
    ) -> None:
        """Run one call-budgeted pass over the org's independently due network/group pairs."""
        by_id = {network["id"]: network for network in networks}
        keys = list(by_id)
        cursors = self._bundle_cursors.setdefault(org_id, {})
        budget = per_attempt_call_budget(self.settings, self.rate_limiter)
        now = monotonic()
        intervals: dict[EndpointGroupName, float] = {}
        due: list[tuple[str, EndpointGroupName]] = []
        for group, cost in _BUNDLE_CALL_COSTS.items():
            cursor = cursors.setdefault(group, FanoutCursor())
            cursor.prune(keys)
            if cost > budget or not self._bundle_group_enabled(group):
                continue
            interval = intervals[group] = float(self._group_interval(group))
            due.extend(
                (key, group)
                for key in cursor.select(
                    keys,
                    interval=interval,
                    retry_spacing=failure_retry_spacing(self.settings, interval),
                    limit=len(keys),
                    now=now,
                )
            )

        def last_served(pair: tuple[str, EndpointGroupName]) -> float:
            key, group = pair
            cursor = cursors[group]
            # Never attempted first; otherwise a failed fetch joins the back of
            # the queue when it becomes retryable, rather than starving siblings.
            return max(
                cursor.last_success.get(key, -math.inf), cursor.last_attempt.get(key, -math.inf)
            )

        due.sort(key=last_served)
        remaining = budget
        selected: dict[str, set[EndpointGroupName]] = {}
        for key, group in due:
            cost = _BUNDLE_CALL_COSTS[group]
            if cost <= remaining:
                selected.setdefault(key, set()).add(group)
                remaining -= cost
                if remaining == 0:
                    break
        if not selected:
            return

        # Size TTLs for the full sweep if the enabled groups all come due
        # together. A two-call group can leave the last slot of a pass unused.
        sweep_calls = len(keys) * sum(_BUNDLE_CALL_COSTS[group] for group in intervals)
        sweep_budget = budget - int(
            sweep_calls > budget
            and budget % _LATENCY_CALLS != 0
            and EndpointGroupName.NH_LATENCY_STATS in intervals
        )
        cadence = self._bundle_cadence_seconds()
        token = self._bundle_ttls.set({
            group: sweep_ttl_seconds(
                self._group_ttl_seconds(group), interval, sweep_calls, sweep_budget, cadence
            )
            for group, interval in intervals.items()
        })
        try:
            results = await process_in_batches_with_errors(
                [by_id[key] for key in selected],
                functools.partial(
                    self._collect_network_health_bundle, selected=selected, cursors=cursors
                ),
                batch_size=self.settings.api.network_batch_size,
                delay_between_batches=self.settings.api.batch_delay,
                spread_over_seconds=self._get_smoothing_window(),
                initial_delay=self._get_smoothing_offset(f"{org_id}:network_health"),
                min_batch_delay=self.settings.api.smoothing_min_batch_delay,
                max_batch_delay=self.settings.api.smoothing_max_batch_delay,
                max_concurrency=self.settings.api.concurrency_limit,
                item_description="network health",
                error_context_func=lambda network: {
                    "org_id": org_id,
                    "org_name": org_name,
                    "network_id": network.get("id"),
                    "network_name": network.get("name"),
                },
                on_error=lambda error: self._track_error(categorize_error(error)),
            )
        finally:
            self._bundle_ttls.reset(token)

        # Retain #629 success reporting without letting mark_ran gate the next
        # pass. These self-paced groups never record a group-level admission.
        succeeded_groups: set[EndpointGroupName] = set()
        for _network, result in results:
            if isinstance(result, frozenset):
                succeeded_groups |= result
        for group in succeeded_groups:
            self._mark_group_ran(group)

    async def _collect_network_health_bundle(
        self,
        network: dict[str, Any],
        selected: dict[str, set[EndpointGroupName]],
        cursors: dict[EndpointGroupName, FanoutCursor],
    ) -> frozenset[EndpointGroupName]:
        """Run the budgeted groups for a network, stamping each successful fetch in place."""
        # (group, per-network collect coroutine factory) in bundle order.
        group_calls: tuple[
            tuple[EndpointGroupName, Callable[[dict[str, Any]], Awaitable[None]]], ...
        ] = (
            (EndpointGroupName.NH_CONNECTION_STATS, self._collect_network_connection_stats),
            (EndpointGroupName.NH_DATA_RATES, self._collect_network_data_rates),
            (EndpointGroupName.NH_BLUETOOTH, self._collect_network_bluetooth_clients),
            (EndpointGroupName.NH_FAILED_CONNECTIONS, self._collect_network_ssid_performance),
            (EndpointGroupName.NH_LATENCY_STATS, self._collect_network_latency_stats),
            (EndpointGroupName.NH_AIR_MARSHAL, self._collect_network_air_marshal),
            (EndpointGroupName.NH_MESH, self._collect_network_mesh),
        )

        network_id = network["id"]
        succeeded: set[EndpointGroupName] = set()
        for group, collect in group_calls:
            if group not in selected[network_id]:
                continue
            cursor = cursors[group]
            cursor.record_attempt(network_id, monotonic())
            try:
                await collect(network)
            except Exception as exc:
                # Per-network per-group failure: isolate it so sibling groups
                # (and other networks) still run, mirror the fan-out's #621
                # error accounting, and record no success for this group here.
                self._track_error(categorize_error(exc))
                logger.debug(
                    "Network-health group fetch failed for network",
                    group=group.value,
                    network_id=network.get("id"),
                    network_name=network.get("name"),
                )
            else:
                cursor.record_success(network_id, monotonic())
                succeeded.add(group)
        return frozenset(succeeded)

    async def _fetch_networks_for_health(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch networks for health collection via shared inventory cache.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of networks.

        Raises
        ------
        RuntimeError
            If inventory service is not configured.

        """
        if not self.inventory:
            raise RuntimeError(
                "Inventory service not configured for NetworkHealthCollector. "
                "This is a programming error - collectors must be initialized with inventory service."
            )

        # No _track_api_call here: inventory.get_networks() is served from the
        # inventory cache (the cache accounts for its own real upstream calls);
        # counting it here inflated the exporter's API-budget telemetry on cache hits.
        return await self.inventory.get_networks(org_id)

    async def _collect_network_connection_stats(self, network: dict[str, Any]) -> None:
        """Collect network-wide wireless connection statistics.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.connection_stats_collector.collect(network)

    async def _collect_network_data_rates(self, network: dict[str, Any]) -> None:
        """Collect network-wide wireless data rate metrics.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.data_rates_collector.collect(network)

    async def _collect_network_bluetooth_clients(self, network: dict[str, Any]) -> None:
        """Collect Bluetooth clients detected by MR devices in a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.bluetooth_collector.collect(network)

    async def _collect_network_ssid_performance(self, network: dict[str, Any]) -> None:
        """Collect per-SSID wireless performance metrics for a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.ssid_performance_collector.collect(network)

    async def _collect_network_latency_stats(self, network: dict[str, Any]) -> None:
        """Collect network-wide wireless latency stats (per-AP + client aggregate).

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.latency_stats_collector.collect(network)

    async def _collect_network_air_marshal(self, network: dict[str, Any]) -> None:
        """Collect Air Marshal rogue-AP / SSID-spoofing detection counts for a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.air_marshal_collector.collect(network)

    async def _collect_network_mesh(self, network: dict[str, Any]) -> None:
        """Collect wireless mesh link health for a network's repeater APs (#307).

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.mesh_collector.collect(network)
