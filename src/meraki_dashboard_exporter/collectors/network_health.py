"""Medium-tier network health metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.async_utils import ManagedTaskGroup
from ..core.batch_processing import process_in_batches_with_errors
from ..core.collector import MetricCollector
from ..core.constants import NetworkHealthMetricName, NetworkMetricName, ProductType, UpdateTier
from ..core.error_handling import ErrorCategory, NothingCollectedError, with_error_handling
from ..core.logging import get_logger
from ..core.logging_decorators import log_batch_operation
from ..core.logging_helpers import log_metric_collection_summary
from ..core.metrics import LabelName
from ..core.otel_tracing import trace_method
from ..core.registry import register_collector
from .network_health_collectors.air_marshal import AirMarshalCollector
from .network_health_collectors.bluetooth import BluetoothCollector
from .network_health_collectors.connection_stats import ConnectionStatsCollector
from .network_health_collectors.data_rates import DataRatesCollector
from .network_health_collectors.latency_stats import LatencyStatsCollector
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


@register_collector(UpdateTier.MEDIUM)
class NetworkHealthCollector(MetricCollector):
    """Collector for medium-moving network health metrics."""

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
        inventory: OrganizationInventory | None = None,
        expiration_manager: MetricExpirationManager | None = None,
        rate_limiter: Any | None = None,
        org_health_tracker: OrgHealthTracker | None = None,
    ) -> None:
        """Initialize network health collector with sub-collectors."""
        super().__init__(api, settings, registry, inventory, expiration_manager, rate_limiter)

        # Shared per-org health tracker (F-169 / #547): when present, per-org
        # collection is skipped for organizations currently in backoff, AND this
        # collector reports its own per-org verdict into the tracker under the
        # SOURCE_NETWORK_HEALTH failure domain so network-endpoint failures engage
        # backoff even when the organization collector is healthy or disabled.
        self.org_health_tracker = org_health_tracker

        # Initialize sub-collectors
        self.rf_health_collector = RFHealthCollector(self)
        self.connection_stats_collector = ConnectionStatsCollector(self)
        self.data_rates_collector = DataRatesCollector(self)
        self.bluetooth_collector = BluetoothCollector(self)
        self.ssid_performance_collector = SSIDPerformanceCollector(self)
        self.latency_stats_collector = LatencyStatsCollector(self)
        self.air_marshal_collector = AirMarshalCollector(self)

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
                    and not self.org_health_tracker.should_collect(org_id)
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
                return

            await process_in_batches_with_errors(
                wireless_networks,
                self._collect_network_health_bundle,
                batch_size=self.settings.api.network_batch_size,
                delay_between_batches=self.settings.api.batch_delay,
                spread_over_seconds=self._get_smoothing_window(),
                initial_delay=self._get_smoothing_offset(f"{org_id}:network_health"),
                min_batch_delay=self.settings.api.smoothing_min_batch_delay,
                max_batch_delay=self.settings.api.smoothing_max_batch_delay,
                item_description="network health",
                error_context_func=lambda network: {
                    "org_id": org_id,
                    "org_name": org_name or org_id,
                    "network_id": network.get("id"),
                    "network_name": network.get("name"),
                },
            )
        except Exception:
            nh_failed = True
            raise
        finally:
            self._record_org_health_verdict(org_id, org_name or org_id, success=not nh_failed)

    def _record_org_health_verdict(self, org_id: str, org_name: str, *, success: bool) -> None:
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

        """
        if self.org_health_tracker is None:
            return
        if success:
            self.org_health_tracker.record_success(org_id, org_name, source=SOURCE_NETWORK_HEALTH)
        else:
            self.org_health_tracker.record_failure(org_id, org_name, source=SOURCE_NETWORK_HEALTH)

    async def _collect_network_health_bundle(self, network: dict[str, Any]) -> None:
        """Collect all network health sub-metrics for a single network."""
        await self._collect_network_rf_health(network)
        await self._collect_network_connection_stats(network)
        await self._collect_network_data_rates(network)
        await self._collect_network_bluetooth_clients(network)
        await self._collect_network_ssid_performance(network)
        await self._collect_network_latency_stats(network)
        await self._collect_network_air_marshal(network)

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

    async def _collect_network_rf_health(self, network: dict[str, Any]) -> None:
        """Collect RF health metrics for a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.rf_health_collector.collect(network)

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
