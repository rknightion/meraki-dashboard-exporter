"""Organization-level metric collector."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any, ClassVar, cast

from ..core.api_helpers import create_api_helper
from ..core.async_utils import ManagedTaskGroup
from ..core.collector import MetricCollector
from ..core.constants import DeviceMetricName, NetworkMetricName, OrgMetricName, UpdateTier
from ..core.constants.metrics_constants import CollectorMetricName
from ..core.error_handling import (
    CollectorError,
    DataValidationError,
    ErrorCategory,
    NothingCollectedError,
    validate_response_format,
    with_error_handling,
)
from ..core.label_helpers import create_org_labels
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call, log_batch_operation
from ..core.logging_helpers import LogContext, log_metric_collection_summary
from ..core.metrics import LabelName, create_labels
from ..core.org_health import SOURCE_ORGANIZATION, OrgHealthTracker
from ..core.otel_tracing import trace_method
from ..core.registry import register_collector
from ..core.scheduler import EndpointGroup, EndpointGroupName, pages
from .organization_collectors import (
    APIUsageCollector,
    ClientOverviewCollector,
    DeviceAvailabilityHistoryCollector,
    FirmwareCollector,
    LicenseCollector,
    TopUsageCollector,
    WebhookLogsCollector,
)

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager
    from ..services.inventory import OrganizationInventory

logger = get_logger(__name__)

# getOrganizationSummaryTopApplicationsCategoriesByUsage documents "Maximum is 50"
# for `quantity` (SDK 3.2.0 docstring) -- see bug-bash finding F-042.
_APPLICATION_USAGE_MAX_QUANTITY = 50


@register_collector(UpdateTier.MEDIUM)
class OrganizationCollector(MetricCollector):
    """Collector for organization-level metrics."""

    # #617 §2 — org endpoint groups (fetch-site gated below). All MEDIUM tier;
    # cost_fn estimates API calls per one execution over the org shape.
    endpoint_groups: ClassVar[tuple[EndpointGroup, ...]] = (
        EndpointGroup(
            name=EndpointGroupName.ORG_AVAILABILITIES,
            priority=1,
            floor_seconds=120,
            cost_fn=lambda shape: pages(shape.device_count, 500),
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_AVAILABILITY_HISTORY,
            priority=2,
            floor_seconds=300,
            cost_fn=lambda shape: 1,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_API_USAGE,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda shape: 2,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_CLIENT_OVERVIEW,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda shape: 1,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_DEVICE_MODEL_OVERVIEW,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda shape: 1,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_PACKET_CAPTURES,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda shape: 1,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_APP_USAGE,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda shape: 1,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_FIRMWARE,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda shape: 1,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_LICENSES,
            priority=4,
            floor_seconds=1800,
            cost_fn=lambda shape: 2,
            tier=UpdateTier.MEDIUM,
        ),
        # Phase 4 (#618) — single/fixed org calls, so cost_fns are org-wide
        # constants rather than shape-derived.
        EndpointGroup(
            name=EndpointGroupName.ORG_CONFIG_TEMPLATES,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda shape: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_ADAPTIVE_POLICY,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda shape: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_TOP_USAGE,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda shape: 3.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_WEBHOOK_LOGS,
            priority=4,
            floor_seconds=300,
            cost_fn=lambda shape: 1.0,
            tier=UpdateTier.MEDIUM,
        ),
        EndpointGroup(
            name=EndpointGroupName.ORG_FIRMWARE_COMPLIANCE,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda shape: 1.0,
            tier=UpdateTier.MEDIUM,
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
        org_health_tracker: OrgHealthTracker | None = None,
    ) -> None:
        """Initialize organization collector with sub-collectors."""
        super().__init__(
            api,
            settings,
            registry,
            inventory,
            expiration_manager,
            rate_limiter,
            scheduler=scheduler,
        )

        # Per-org health tracker for graceful degradation
        self.org_health_tracker = org_health_tracker or OrgHealthTracker()

        # Create API helper
        self.api_helper = create_api_helper(self)

        # Initialize sub-collectors
        self.api_usage_collector = APIUsageCollector(self)
        self.license_collector = LicenseCollector(self)
        self.client_overview_collector = ClientOverviewCollector(self)
        self.firmware_collector = FirmwareCollector(self)
        self.device_availability_history_collector = DeviceAvailabilityHistoryCollector(self)
        self.top_usage_collector = TopUsageCollector(self)
        self.webhook_logs_collector = WebhookLogsCollector(self)

    def _initialize_metrics(self) -> None:
        """Initialize organization metrics."""
        # Per-org collection health status (1=success, 0=failed/backed-off)
        self._org_collection_status = self._create_gauge(
            CollectorMetricName.EXPORTER_ORG_COLLECTION_STATUS,
            "Organization collection status (1=success, 0=failed or in backoff)",
            labelnames=[LabelName.ORG_ID],
        )

        # Organization info -- canonical org-name carrier; keeps org_name (#534
        # KEEP). Numeric series join back via meraki_org_info on org_id.
        self._org_info = self._create_info(
            OrgMetricName.ORG_INFO,
            "Organization information",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        # Network info -- the id->name join backbone (#534 NI-1). Constant value
        # 1, one series per NetworkFilter-allowed network. network_name joins via
        # `<numeric> * on(network_id) group_left(network_name) meraki_network_info`.
        self._network_info = self._create_gauge(
            NetworkMetricName.NETWORK_INFO,
            "Network information (join metric: network_id -> network_name)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        # API metrics
        self._api_requests_total = self._create_gauge(
            OrgMetricName.ORG_API_REQUESTS_COUNT,
            "Meraki-reported total API requests made by ALL clients of this organization's "
            "Dashboard API (any app/integration, not just this exporter) in the trailing 1-hour "
            "window; a snapshot count, not a monotonic counter",
            labelnames=[LabelName.ORG_ID],
        )

        self._api_requests_by_status = self._create_gauge(
            OrgMetricName.ORG_API_REQUESTS_BY_STATUS,
            "API requests by HTTP status code in the last hour",
            labelnames=[LabelName.ORG_ID, LabelName.STATUS_CODE],
        )

        # Network metrics
        self._networks_total = self._create_gauge(
            OrgMetricName.ORG_NETWORKS,
            "Number of networks in the organization",
            labelnames=[LabelName.ORG_ID],
        )

        # Device metrics
        self._devices_total = self._create_gauge(
            OrgMetricName.ORG_DEVICES,
            "Number of devices in the organization",
            labelnames=[LabelName.ORG_ID, LabelName.DEVICE_TYPE],
        )

        self._devices_by_model_total = self._create_gauge(
            OrgMetricName.ORG_DEVICES_BY_MODEL,
            "Number of devices by specific model",
            labelnames=[LabelName.ORG_ID, LabelName.MODEL],
        )

        # Device availability metrics (from new API)
        self._devices_availability_total = self._create_gauge(
            OrgMetricName.ORG_DEVICES_AVAILABILITY,
            "Number of devices by availability status and product type",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.STATUS,
                LabelName.PRODUCT_TYPE,
            ],
        )

        # Device availability change history (windowed transition counts per poll)
        self._org_devices_availability_changes_total = self._create_gauge(
            OrgMetricName.ORG_DEVICES_AVAILABILITY_CHANGES_COUNT,
            "Number of device availability transitions observed in the collection window "
            "(tied to the configured MEDIUM update interval, default 300s) by product type "
            "and new status",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.PRODUCT_TYPE,
                LabelName.STATUS,
            ],
        )

        # Firmware upgrade tracking
        self._org_firmware_upgrades_total = self._create_gauge(
            OrgMetricName.ORG_FIRMWARE_UPGRADES,
            "Number of firmware upgrade events by product type and status",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.PRODUCT_TYPE,
                LabelName.STATUS,
            ],
        )
        self._org_firmware_upgrades_pending_total = self._create_gauge(
            OrgMetricName.ORG_FIRMWARE_UPGRADES_PENDING,
            "Number of pending/in-flight firmware upgrade events by product type",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.PRODUCT_TYPE,
            ],
        )

        # License metrics
        self._licenses_total = self._create_gauge(
            OrgMetricName.ORG_LICENSES,
            "Number of licenses",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.LICENSE_TYPE,
                LabelName.STATUS,
            ],
        )

        self._licenses_expiring = self._create_gauge(
            OrgMetricName.ORG_LICENSES_EXPIRING,
            "Number of licenses expiring within 30 days",
            labelnames=[LabelName.ORG_ID, LabelName.LICENSE_TYPE],
        )

        # Client metrics
        self._clients_total = self._create_gauge(
            OrgMetricName.ORG_CLIENTS_COUNT,
            "Number of active clients in the organization in the last hour",
            labelnames=[LabelName.ORG_ID],
        )

        # Usage metrics (in bytes for the 1-hour window)
        self._usage_total_kb = self._create_gauge(
            OrgMetricName.ORG_USAGE_TOTAL_BYTES,
            "Total data usage in bytes for the 1-hour window",
            labelnames=[LabelName.ORG_ID],
        )

        self._usage_downstream_kb = self._create_gauge(
            OrgMetricName.ORG_USAGE_DOWNSTREAM_BYTES,
            "Downstream data usage in bytes for the 1-hour window",
            labelnames=[LabelName.ORG_ID],
        )

        self._usage_upstream_kb = self._create_gauge(
            OrgMetricName.ORG_USAGE_UPSTREAM_BYTES,
            "Upstream data usage in bytes for the 1-hour window",
            labelnames=[LabelName.ORG_ID],
        )

        # Packet capture metrics
        self._packetcaptures_total = self._create_gauge(
            OrgMetricName.ORG_PACKETCAPTURES,
            "Number of packet captures in the organization",
            labelnames=[LabelName.ORG_ID],
        )

        self._packetcaptures_remaining = self._create_gauge(
            OrgMetricName.ORG_PACKETCAPTURES_REMAINING,
            "Number of remaining packet captures to process",
            labelnames=[LabelName.ORG_ID],
        )

        # Application usage metrics (API default rolling window is 1 day)
        self._application_usage_total_mb = self._create_gauge(
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_BYTES,
            "Total application usage in bytes by category over the trailing 1-day window",
            labelnames=[LabelName.ORG_ID, LabelName.CATEGORY],
        )

        self._application_usage_downstream_mb = self._create_gauge(
            OrgMetricName.ORG_APPLICATION_USAGE_DOWNSTREAM_BYTES,
            "Downstream application usage in bytes by category over the trailing 1-day window",
            labelnames=[LabelName.ORG_ID, LabelName.CATEGORY],
        )

        self._application_usage_upstream_mb = self._create_gauge(
            OrgMetricName.ORG_APPLICATION_USAGE_UPSTREAM_BYTES,
            "Upstream application usage in bytes by category over the trailing 1-day window",
            labelnames=[LabelName.ORG_ID, LabelName.CATEGORY],
        )

        self._application_usage_percentage = self._create_gauge(
            OrgMetricName.ORG_APPLICATION_USAGE_PERCENT,
            "Application usage percent by category over the trailing 1-day window",
            labelnames=[LabelName.ORG_ID, LabelName.CATEGORY],
        )

        # --- Phase 4 (#618) organization signal expansion ---

        # #297 — Config templates + template binding.
        self._org_config_templates = self._create_gauge(
            OrgMetricName.ORG_CONFIG_TEMPLATES,
            "Number of configuration templates defined in the organization",
            labelnames=[LabelName.ORG_ID],
        )
        self._org_networks_bound_to_template = self._create_gauge(
            OrgMetricName.ORG_NETWORKS_BOUND_TO_TEMPLATE,
            "Number of NetworkFilter-visible networks bound to a configuration template "
            "(counts only networks within the configured NetworkFilter, not the whole org)",
            labelnames=[LabelName.ORG_ID],
        )

        # #298 — Adaptive policy overview (absent unless the org is licensed for
        # adaptive policy; the endpoint 404s otherwise and the metrics stay unset).
        self._org_adaptive_policy_groups = self._create_gauge(
            OrgMetricName.ORG_ADAPTIVE_POLICY_GROUPS,
            "Number of adaptive policy groups in the organization",
            labelnames=[LabelName.ORG_ID],
        )
        self._org_adaptive_policy_acls = self._create_gauge(
            OrgMetricName.ORG_ADAPTIVE_POLICY_ACLS,
            "Number of adaptive policy custom ACLs in the organization",
            labelnames=[LabelName.ORG_ID],
        )
        self._org_adaptive_policy_policies = self._create_gauge(
            OrgMetricName.ORG_ADAPTIVE_POLICY_POLICIES,
            "Number of adaptive policies in the organization",
            labelnames=[LabelName.ORG_ID],
        )

        # #299 — Org-wide top-N usage over the trailing 1-day window. Bounded to
        # the top 10 entries per dimension.
        self._org_top_client_usage_total_bytes = self._create_gauge(
            OrgMetricName.ORG_TOP_CLIENT_USAGE_TOTAL_BYTES,
            "Total bytes used by each top-N client over the trailing 1-day window "
            "(labelled by client_id only per #533; join client_id -> name via "
            "meraki_client_info, which may miss clients on untracked networks)",
            labelnames=[LabelName.ORG_ID, LabelName.CLIENT_ID],
        )
        self._org_top_ssid_usage_total_bytes = self._create_gauge(
            OrgMetricName.ORG_TOP_SSID_USAGE_TOTAL_BYTES,
            "Total bytes used by each top-N SSID over the trailing 1-day window",
            labelnames=[LabelName.ORG_ID, LabelName.SSID],
        )
        self._org_top_manufacturer_usage_total_bytes = self._create_gauge(
            OrgMetricName.ORG_TOP_MANUFACTURER_USAGE_TOTAL_BYTES,
            "Total bytes used by each top-N client-device manufacturer over the "
            "trailing 1-day window",
            labelnames=[LabelName.ORG_ID, LabelName.MANUFACTURER],
        )

        # #300 — Webhook delivery log. Windowed 1-hour count of delivery attempts
        # by HTTP response status code, resampled each cycle (a _count, not a
        # monotonic _total). Deliveries with a non-2xx code are failures
        # (status_code!~"2.." in PromQL); the URL is deliberately not a label.
        self._org_webhook_deliveries_count = self._create_gauge(
            OrgMetricName.ORG_WEBHOOK_DELIVERIES_COUNT,
            "Number of Meraki webhook delivery attempts in the trailing 1-hour window "
            "by HTTP response status code (windowed count, resets each cycle; failures "
            'are status_code!~"2..")',
            labelnames=[LabelName.ORG_ID, LabelName.STATUS_CODE],
        )

        # #611 — Firmware compliance. Per-device firmware info join carrier (value
        # 1, one series per device, joins on serial) and a per-network up-to-date
        # gauge derived from the firmware-upgrades-by-device endpoint.
        self._device_firmware_info = self._create_gauge(
            DeviceMetricName.DEVICE_FIRMWARE_INFO,
            "Device firmware join metric (value 1): maps serial -> running firmware. "
            "Numeric device series join firmware via on(serial) group_left(firmware)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.FIRMWARE,
            ],
        )
        self._network_firmware_up_to_date = self._create_gauge(
            NetworkMetricName.NETWORK_FIRMWARE_UP_TO_DATE,
            "Whether every device in the network is on its latest firmware "
            "(1=all up to date / no pending upgrade, 0=at least one device has a "
            "pending or in-progress upgrade)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID],
        )

    async def _collect_impl(self) -> None:
        """Collect organization metrics with parallel organization processing.

        Organizations are processed in parallel with bounded concurrency
        to significantly improve performance for multi-org deployments.
        """
        start_time = asyncio.get_event_loop().time()
        metrics_collected = 0
        organizations_processed = 0
        api_calls_made = 0

        # Get organizations. No blanket try/except here (#509): a failure to
        # fetch organizations is a genuine collection failure and must raise
        # out of _collect_impl so the manager records the cycle as a failure
        # instead of a spurious success.
        organizations = await self._fetch_organizations()
        if not organizations:
            logger.warning("No organizations found to collect metrics from")
            return
        api_calls_made += 1

        logger.info(
            "Starting parallel organization processing",
            org_count=len(organizations),
            concurrency_limit=self.settings.api.concurrency_limit,
        )

        # Process organizations in parallel with bounded concurrency. Orgs
        # currently in OrgHealthTracker backoff are skipped HERE, before the
        # worker coroutine is even constructed (not inside the worker), so an
        # all-orgs-in-backoff cycle can be distinguished from a genuine
        # success by the frozen coordinator failure rule below (#509).
        skipped_backoff = 0
        async with ManagedTaskGroup(
            name="org_collector_orgs",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for org in organizations:
                org_id = org["id"]
                if not self.org_health_tracker.should_collect(org_id):
                    health = self.org_health_tracker.get_health(org_id)
                    logger.info(
                        "Skipping organization collection due to backoff",
                        org_id=org_id,
                        org_name=org.get("name"),
                        consecutive_failures=health.consecutive_failures if health else 0,
                    )
                    self._org_collection_status.labels(**create_org_labels(org)).set(0)
                    skipped_backoff += 1
                    continue
                await group.create_task(
                    self._collect_org_metrics(org),
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
        api_calls_made += organizations_processed * 7

        # Log collection summary
        log_metric_collection_summary(
            "OrganizationCollector",
            metrics_collected=metrics_collected,
            duration_seconds=asyncio.get_event_loop().time() - start_time,
            organizations_processed=organizations_processed,
            api_calls_made=api_calls_made,
        )

    async def _fetch_organizations(self) -> list[dict[str, Any]] | None:
        """Fetch organizations using inventory cache.

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
                "Inventory service not configured for OrganizationCollector. "
                "This is a programming error - collectors must be initialized with inventory service."
            )

        return await self.inventory.get_organizations()

    @trace_method("process.organization")
    @log_batch_operation("collect org metrics", batch_size=1)
    @with_error_handling(
        operation="Collect organization metrics",
        continue_on_error=False,
    )
    async def _collect_org_metrics(self, org: dict[str, Any]) -> None:
        """Collect metrics for a specific organization.

        Note: the OrgHealthTracker backoff check has moved to the coordinator
        (`_collect_impl`), which now skips backed-off orgs before this worker
        is even scheduled (#509) -- so this method no longer needs to check
        `should_collect` itself.

        Parameters
        ----------
        org : dict[str, Any]
            Organization data.

        """
        org_id = org["id"]
        org_name = org["name"]

        org_labels = create_org_labels(org)

        try:
            with LogContext(org_id=org_id, org_name=org_name):
                # Set organization info. This is the canonical org-name carrier
                # (#534 KEEP), so its label dict is built explicitly WITH
                # org_name rather than via the ID-only create_org_labels helper.
                if self._org_info:
                    info_labels = create_labels(org_id=org_id, org_name=org_name)
                    self._org_info.labels(**info_labels).info({
                        "url": org.get("url", ""),
                        "api_enabled": str(org.get("api", {}).get("enabled", False)),
                    })
                else:
                    logger.error("_org_info metric not initialized")

                # Collect every sub-collection, tracking (not raising) failures so
                # one broken endpoint never prevents the rest of this org's metrics
                # from being collected.
                (
                    failed_sub_collections,
                    succeeded_sub_collections,
                ) = await self._run_org_sub_collections(org_id, org_name)

            if failed_sub_collections:
                # At least one sub-collection failed with a real (non-404) error
                # this cycle. Previously every sub-collection swallowed its own
                # exceptions, so this branch -- and OrgHealthTracker.record_failure
                # / exporter_org_collection_status=0 -- could never trigger even
                # when an org's API access was completely broken (bug-bash F-040).
                logger.warning(
                    "One or more sub-collections failed for organization",
                    org_id=org_id,
                    org_name=org_name,
                    failed_sub_collections=failed_sub_collections,
                )
                self.org_health_tracker.record_failure(org_id, org_name, source=SOURCE_ORGANIZATION)
                self._org_collection_status.labels(**org_labels).set(0)
            else:
                self.org_health_tracker.record_success(org_id, org_name, source=SOURCE_ORGANIZATION)
                self._org_collection_status.labels(**org_labels).set(1)

        except Exception:
            # Reached for errors outside the individually-tracked sub-collections
            # (e.g. building org_labels or setting _org_info).
            logger.exception(
                "Failed to collect metrics for organization",
                org_id=org_id,
                org_name=org_name,
            )
            self.org_health_tracker.record_failure(org_id, org_name, source=SOURCE_ORGANIZATION)
            self._org_collection_status.labels(**org_labels).set(0)
            raise

        if failed_sub_collections and succeeded_sub_collections == 0:
            # Every sub-collection failed with a real (non-404) error this
            # cycle -- this org contributed nothing this cycle, so this
            # worker must raise to be counted as failed by the coordinator's
            # ManagedTaskGroup (#509). Raised OUTSIDE the try/except above (a
            # deliberate deviation from the spec's literal placement) so
            # OrgHealthTracker.record_failure -- already called once in the
            # F-040 branch above -- is not invoked a second time by the
            # except block re-catching this raise.
            raise CollectorError(
                f"All organization sub-collections failed for org {org_id}",
                ErrorCategory.API_CLIENT_ERROR,
                {"org_id": org_id},
            )

    async def _run_org_sub_collections(self, org_id: str, org_name: str) -> tuple[list[str], int]:
        """Run every per-organization sub-collection, tracking which ones fail.

        Every sub-collection is attempted even if an earlier one failed, so a
        single broken or unavailable endpoint never prevents metrics for the
        rest of the organization from being collected. A 404 (endpoint not
        available for this org -- e.g. packet captures or firmware upgrade
        history not applicable) is treated as expected, not a failure.

        Note: `api_metrics`, `firmware_metrics`,
        `device_availability_changes_metrics`, `license_metrics`, and
        `client_overview` delegate to sub-collectors in
        `organization_collectors/` that swallow their own exceptions (by
        design, for resilience) rather than raising. To keep an isolated
        failure in one of those five observable by ``OrgHealthTracker``
        (bug-bash F-172), each of those delegating wrappers now returns a
        boolean success signal: ``True`` on success or an expected 404, and
        ``False`` on a real (non-404) failure. ``_attempt`` records a wrapper
        that returns ``False`` as a failed sub-collection, alongside the six
        sub-collections implemented directly in this module (which instead
        raise on failure and return ``None`` on success).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        Returns
        -------
        tuple[list[str], int]
            ``(failed, succeeded)`` -- ``failed`` is the names of
            sub-collections that failed with a non-404 error this cycle
            (either by raising, the six direct sub-collections, or by
            returning ``False``, the five delegating sub-collectors); empty
            if every sub-collection succeeded or 404'd. ``succeeded`` is the
            count of sub-collections whose result was not ``False`` (i.e. a
            direct sub-collection returning ``None``, or a delegating
            sub-collector returning ``True``) -- used by the caller (#509) to
            detect an org where every attempted sub-collection failed. A 404
            (``API_NOT_AVAILABLE``) early-return counts as neither failed nor
            succeeded.

        """
        failed: list[str] = []
        succeeded = 0

        async def _attempt(name: str, coro: Coroutine[Any, Any, bool | None]) -> None:
            nonlocal succeeded
            try:
                result = await coro
            except CollectorError as exc:
                if exc.category == ErrorCategory.API_NOT_AVAILABLE:
                    return
                failed.append(name)
            except Exception:
                logger.exception(
                    "Sub-collection failed for organization",
                    org_id=org_id,
                    org_name=org_name,
                    sub_collection=name,
                )
                self._track_error(ErrorCategory.UNKNOWN)
                failed.append(name)
            else:
                # Delegating sub-collectors signal a real (non-404) failure by
                # returning False instead of raising (F-172). The six direct
                # sub-collections return None on success and are unaffected.
                if result is False:
                    failed.append(name)
                else:
                    succeeded += 1

        await _attempt("api_metrics", self._collect_api_metrics(org_id, org_name))
        await _attempt("network_metrics", self._collect_network_metrics(org_id, org_name))
        await _attempt("device_metrics", self._collect_device_metrics(org_id, org_name))
        await _attempt(
            "device_counts_by_model", self._collect_device_counts_by_model(org_id, org_name)
        )
        await _attempt(
            "device_availability_metrics",
            self._collect_device_availability_metrics(org_id, org_name),
        )
        await _attempt(
            "device_availability_changes_metrics",
            self._collect_device_availability_changes_metrics(org_id, org_name),
        )
        await _attempt("firmware_metrics", self._collect_firmware_metrics(org_id, org_name))
        await _attempt("license_metrics", self._collect_license_metrics(org_id, org_name))
        await _attempt("client_overview", self._collect_client_overview(org_id, org_name))
        await _attempt(
            "packet_capture_metrics", self._collect_packet_capture_metrics(org_id, org_name)
        )
        await _attempt(
            "application_usage_metrics",
            self._collect_application_usage_metrics(org_id, org_name),
        )
        # Phase 4 (#618): #297 config templates + #298 adaptive policy are direct
        # sub-collections (raise on failure); #299 top usage, #300 webhook logs and
        # #611 firmware compliance delegate to sub-collectors returning a bool.
        await _attempt("config_templates", self._collect_config_templates(org_id, org_name))
        await _attempt("adaptive_policy", self._collect_adaptive_policy(org_id, org_name))
        await _attempt("top_usage_metrics", self._collect_top_usage_metrics(org_id, org_name))
        await _attempt("webhook_logs_metrics", self._collect_webhook_logs_metrics(org_id, org_name))
        await _attempt(
            "firmware_compliance_metrics",
            self._collect_firmware_compliance_metrics(org_id, org_name),
        )

        return failed, succeeded

    async def _collect_api_metrics(self, org_id: str, org_name: str) -> bool:
        """Collect API usage metrics.

        Returns the sub-collector's success/failure signal so an isolated
        failure here is observable by ``OrgHealthTracker`` (F-172): ``True`` on
        success or an expected 404, ``False`` on a real (non-404) failure. The
        sub-collector owns its own error handling (it never raises), so no
        ``with_error_handling`` wrapper is needed on this thin delegator.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        return await self.api_usage_collector.collect(org_id, org_name) is True

    async def _collect_firmware_metrics(self, org_id: str, org_name: str) -> bool:
        """Collect firmware upgrade status metrics.

        Returns the sub-collector's success/failure signal (see
        ``_collect_api_metrics``) so an isolated failure is counted by
        ``OrgHealthTracker`` (F-172).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        return await self.firmware_collector.collect(org_id, org_name) is True

    async def _collect_device_availability_changes_metrics(
        self, org_id: str, org_name: str
    ) -> bool:
        """Collect device availability change-history (flap) metrics.

        Returns the sub-collector's success/failure signal (see
        ``_collect_api_metrics``) so an isolated failure is counted by
        ``OrgHealthTracker`` (F-172).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        return await self.device_availability_history_collector.collect(org_id, org_name) is True

    @with_error_handling(
        operation="Collect network metrics",
        continue_on_error=False,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_network_metrics(self, org_id: str, org_name: str) -> None:
        """Collect network metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        networks = await self.api_helper.get_organization_networks(org_id)
        if not networks:
            logger.warning("No networks found or error fetching networks", org_id=org_id)
            return

        # Count total networks
        total_networks = len(networks)
        # Create org labels using helper
        org_data = {"id": org_id, "name": org_name}
        org_labels = create_org_labels(org_data)

        if self._networks_total:
            self._networks_total.labels(**org_labels).set(total_networks)
        else:
            logger.error("_networks_total metric not initialized")

        # Emit the network_id -> network_name join backbone (#534 NI-1). One
        # series (value 1) per NetworkFilter-allowed network, straight from the
        # already-fetched filtered list (zero extra API calls). Routed through
        # _set_metric so a deleted/filtered network's series expires instead of
        # freezing forever. This is the id->name carrier every network_name
        # join across the exporter depends on.
        if self._network_info:
            for network in networks:
                network_id = network.get("id", "")
                if not network_id:
                    continue
                info_labels = create_labels(
                    org_id=org_id,
                    network_id=network_id,
                    network_name=network.get("name", ""),
                )
                self._set_metric(
                    self._network_info,
                    info_labels,
                    1,
                    NetworkMetricName.NETWORK_INFO.value,
                )
        else:
            logger.error("_network_info metric not initialized")

    @with_error_handling(
        operation="Collect device metrics",
        continue_on_error=False,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_device_metrics(self, org_id: str, org_name: str) -> None:
        """Collect device metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        devices = await self.api_helper.get_organization_devices(org_id)
        if not devices:
            return

        # Validate response format (handles API error responses like rate limits)
        devices = validate_response_format(
            devices, expected_type=list, operation="getOrganizationDevices"
        )

        # Count devices by type
        device_counts: dict[str, int] = {}
        for device in devices:
            model = device.get("model", "")
            # Extract device type from model (e.g., "MS" from "MS210-8")
            device_type = model[:2] if len(model) >= 2 else "Unknown"
            device_counts[device_type] = device_counts.get(device_type, 0) + 1

        # Set metrics for each device type
        # Create org labels using helper
        org_data = {"id": org_id, "name": org_name}

        if self._devices_total:
            for device_type, count in device_counts.items():
                labels = create_org_labels(
                    org_data,
                    device_type=device_type,
                )
                # Route through _set_metric for expiration tracking so device
                # types that disappear are removed instead of frozen forever.
                self._set_metric(
                    self._devices_total,
                    labels,
                    count,
                    OrgMetricName.ORG_DEVICES.value,
                )
        else:
            logger.error("_devices_total metric not initialized")

    @log_api_call("getOrganizationDevicesOverviewByModel")
    @with_error_handling(
        operation="Collect device counts by model",
        continue_on_error=False,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_device_counts_by_model(self, org_id: str, org_name: str) -> None:
        """Collect device counts by specific model.

        Scoped to the configured NetworkFilter (via ``networkIds``) so this
        metric stays consistent with its inventory-filtered sibling
        ``meraki_org_devices`` instead of always covering the whole org
        (bug-bash finding F-098).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        if not self._should_run_group(EndpointGroupName.ORG_DEVICE_MODEL_OVERVIEW):
            return

        network_ids: list[str] | None = None
        if self.inventory:
            allowed_network_ids = await self.inventory.get_allowed_network_ids(org_id)
            if allowed_network_ids is not None:
                network_ids = sorted(allowed_network_ids)

        with LogContext(org_id=org_id, org_name=org_name):
            kwargs: dict[str, Any] = {}
            if network_ids is not None:
                kwargs["networkIds"] = network_ids

            # This endpoint's documented response is a plain {"counts": [...]}
            # object, but some org bulk endpoints wrap their payload in
            # {"items": [...]} -- handle that shape too rather than silently
            # dropping it (bug-bash finding F-041). Detect the SDK's
            # exhausted-retry error shape inline.
            overview = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesOverviewByModel,
                org_id,
                **kwargs,
            )
            if isinstance(overview, dict) and "errors" in overview:
                raise DataValidationError(
                    "getOrganizationDevicesOverviewByModel: API returned errors: "
                    f"{overview['errors']}",
                    {"errors": overview["errors"]},
                )

        # Fetch succeeded — record the group ran so gating stretches from here.
        self._mark_group_ran(EndpointGroupName.ORG_DEVICE_MODEL_OVERVIEW)
        ttl = self._group_ttl_seconds(EndpointGroupName.ORG_DEVICE_MODEL_OVERVIEW)

        counts: list[dict[str, Any]] | None = None
        if isinstance(overview, dict) and "counts" in overview:
            counts = overview.get("counts", [])
        elif isinstance(overview, dict) and "items" in overview:
            counts = overview["items"]
        else:
            logger.warning(
                "Unexpected response format for device overview by model",
                org_id=org_id,
                response_type=type(overview).__name__,
            )
            return

        if not counts:
            logger.debug("No device-by-model counts returned", org_id=org_id)
            return

        # Create org labels using helper
        org_data = {"id": org_id, "name": org_name}

        if self._devices_by_model_total:
            for model_data in counts:
                model = model_data.get("model", "Unknown")
                count = model_data.get("total", 0)
                labels = create_org_labels(
                    org_data,
                    model=model,
                )
                # Route through _set_metric so models that drop out of the
                # fleet expire instead of freezing at their last count.
                self._set_metric(
                    self._devices_by_model_total,
                    labels,
                    count,
                    OrgMetricName.ORG_DEVICES_BY_MODEL.value,
                    ttl_seconds=ttl,
                )
        else:
            logger.error("_devices_by_model_total metric not initialized")

    async def _collect_license_metrics(self, org_id: str, org_name: str) -> bool:
        """Collect license metrics.

        Returns the sub-collector's success/failure signal (see
        ``_collect_api_metrics``) so an isolated failure is counted by
        ``OrgHealthTracker`` (F-172).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        return await self.license_collector.collect(org_id, org_name) is True

    @with_error_handling(
        operation="Collect device availability metrics",
        continue_on_error=False,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_device_availability_metrics(self, org_id: str, org_name: str) -> None:
        """Collect device availability metrics.

        Uses inventory cache if available (2-min TTL), otherwise falls back to direct API call.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        if not self._should_run_group(EndpointGroupName.ORG_AVAILABILITIES):
            return

        with LogContext(org_id=org_id, org_name=org_name):
            # Use inventory cache if available
            if self.inventory:
                logger.debug("Using inventory cache for device availabilities", org_id=org_id)
                availabilities = await self.inventory.get_device_availabilities(org_id)
            else:
                logger.debug(
                    "Inventory not available, fetching availabilities directly", org_id=org_id
                )
                availabilities_response = await asyncio.to_thread(
                    self.api.organizations.getOrganizationDevicesAvailabilities,
                    org_id,
                    total_pages="all",
                )
                availabilities = cast(
                    list[dict[str, Any]],
                    validate_response_format(
                        availabilities_response,
                        expected_type=list,
                        operation="getOrganizationDevicesAvailabilities",
                    ),
                )

        # Fetch succeeded — record the group ran so gating stretches from here.
        self._mark_group_ran(EndpointGroupName.ORG_AVAILABILITIES)
        ttl = self._group_ttl_seconds(EndpointGroupName.ORG_AVAILABILITIES)

        # Group by status and product type
        availability_counts: dict[tuple[str, str], int] = {}
        for device in availabilities:
            status = device.get("status", "unknown")
            product_type = device.get("productType", "unknown")
            key = (status, product_type)
            availability_counts[key] = availability_counts.get(key, 0) + 1

        # Set metrics for each combination
        # Create org labels using helper
        org_data = {"id": org_id, "name": org_name}

        if self._devices_availability_total:
            for (status, product_type), count in availability_counts.items():
                labels = create_org_labels(
                    org_data,
                    status=status,
                    product_type=product_type,
                )
                # Route through _set_metric so absent status/product-type combos
                # expire instead of holding a stale count forever.
                self._set_metric(
                    self._devices_availability_total,
                    labels,
                    count,
                    OrgMetricName.ORG_DEVICES_AVAILABILITY.value,
                    ttl_seconds=ttl,
                )
        else:
            logger.error("_devices_availability_total metric not initialized")

    async def _collect_client_overview(self, org_id: str, org_name: str) -> bool:
        """Collect client overview metrics.

        Returns the sub-collector's success/failure signal (see
        ``_collect_api_metrics``) so an isolated failure is counted by
        ``OrgHealthTracker`` (F-172).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        return await self.client_overview_collector.collect(org_id, org_name) is True

    @log_api_call("getOrganizationDevicesPacketCaptureCaptures")
    @with_error_handling(
        operation="Collect packet capture metrics",
        continue_on_error=False,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_packet_capture_metrics(self, org_id: str, org_name: str) -> None:
        """Collect packet capture metrics.

        Scoped to the configured NetworkFilter (via ``networkIds``) so packet
        capture counts stay consistent with the exporter's other
        inventory-filtered org metrics instead of always covering the whole
        org (bug-bash finding F-098).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        if not self._should_run_group(EndpointGroupName.ORG_PACKET_CAPTURES):
            return

        network_ids: list[str] | None = None
        if self.inventory:
            allowed_network_ids = await self.inventory.get_allowed_network_ids(org_id)
            if allowed_network_ids is not None:
                network_ids = sorted(allowed_network_ids)

        with LogContext(org_id=org_id, org_name=org_name):
            # Use perPage=3 to minimize data transfer while still getting the meta counts.
            # Note: this endpoint returns {"items": [...], "meta": {...}}, so we cannot
            # use validate_response_format (which unwraps "items"). Check for the
            # SDK's exhausted-retry error shape inline instead.
            kwargs: dict[str, Any] = {"perPage": 3}
            if network_ids is not None:
                kwargs["networkIds"] = network_ids
            response = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesPacketCaptureCaptures,
                org_id,
                **kwargs,
            )
            if isinstance(response, dict) and "errors" in response:
                raise DataValidationError(
                    "getOrganizationDevicesPacketCaptureCaptures: API returned errors: "
                    f"{response['errors']}",
                    {"errors": response["errors"]},
                )

        # Fetch succeeded — record the group ran so gating stretches from here.
        # (These two gauges use direct .set(), not _set_metric, so no per-series
        # TTL applies — they never enter expiration tracking.)
        self._mark_group_ran(EndpointGroupName.ORG_PACKET_CAPTURES)

        # Extract meta counts
        if isinstance(response, dict) and "meta" in response and "counts" in response["meta"]:
            counts = response["meta"]["counts"].get("items", {})
            total = counts.get("total", 0)
            remaining = counts.get("remaining", 0)

            # Set metrics
            # Create org labels using helper
            org_data = {"id": org_id, "name": org_name}
            org_labels = create_org_labels(org_data)

            if self._packetcaptures_total:
                self._packetcaptures_total.labels(**org_labels).set(total)
            else:
                logger.error("_packetcaptures_total metric not initialized")

            if self._packetcaptures_remaining:
                self._packetcaptures_remaining.labels(**org_labels).set(remaining)
            else:
                logger.error("_packetcaptures_remaining metric not initialized")

            logger.debug(
                "Collected packet capture metrics",
                org_id=org_id,
                total=total,
                remaining=remaining,
            )
        else:
            logger.warning(
                "Unexpected response format for packet captures",
                org_id=org_id,
                response_type=type(response).__name__,
            )

    def _sanitize_category_name(self, category: str) -> str:
        """Sanitize category name for use as a Prometheus label.

        Parameters
        ----------
        category : str
            Raw category name from API.

        Returns
        -------
        str
            Sanitized category name.

        """
        if not category:
            return "unknown"

        # Convert to lowercase and replace problematic characters
        sanitized = category.lower()
        sanitized = sanitized.replace(" & ", "_and_")
        sanitized = sanitized.replace("&", "_and_")
        sanitized = sanitized.replace(" - ", "_")
        sanitized = sanitized.replace("-", "_")
        sanitized = sanitized.replace(" ", "_")
        sanitized = sanitized.replace("/", "_")
        sanitized = sanitized.replace("\\", "_")
        sanitized = sanitized.replace(".", "")
        sanitized = sanitized.replace(",", "")
        sanitized = sanitized.replace(":", "")
        sanitized = sanitized.replace(";", "")
        sanitized = sanitized.replace("(", "")
        sanitized = sanitized.replace(")", "")
        sanitized = sanitized.replace("'", "")
        sanitized = sanitized.replace('"', "")

        # Remove any remaining non-alphanumeric characters except underscore
        result = ""
        for char in sanitized:
            if char.isalnum() or char == "_":
                result += char

        # Remove multiple underscores
        while "__" in result:
            result = result.replace("__", "_")

        # Strip leading/trailing underscores
        result = result.strip("_")

        return result if result else "unknown"

    @log_api_call("getOrganizationSummaryTopApplicationsCategoriesByUsage")
    @with_error_handling(
        operation="Collect application usage metrics",
        continue_on_error=False,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_application_usage_metrics(self, org_id: str, org_name: str) -> None:
        """Collect application usage metrics by category.

        ``quantity`` is clamped to ``_APPLICATION_USAGE_MAX_QUANTITY`` (50),
        the documented API maximum for
        ``getOrganizationSummaryTopApplicationsCategoriesByUsage`` (bug-bash
        finding F-042). No ``timespan`` is passed, so values reflect the
        API's default 1-day rolling window.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        if not self._should_run_group(EndpointGroupName.ORG_APP_USAGE):
            return

        with LogContext(org_id=org_id, org_name=org_name):
            raw_response = await asyncio.to_thread(
                self.api.organizations.getOrganizationSummaryTopApplicationsCategoriesByUsage,
                org_id,
                quantity=_APPLICATION_USAGE_MAX_QUANTITY,
            )
            response = cast(
                list[dict[str, Any]],
                validate_response_format(
                    raw_response,
                    expected_type=list,
                    operation="getOrganizationSummaryTopApplicationsCategoriesByUsage",
                ),
            )

        # Fetch succeeded — record the group ran so gating stretches from here.
        # (These gauges use direct .set(), not _set_metric, so no per-series TTL.)
        self._mark_group_ran(EndpointGroupName.ORG_APP_USAGE)

        # Process each category
        for category_data in response:
            category = category_data.get("category", "Unknown")
            sanitized_category = self._sanitize_category_name(category)

            # API values are in MB; convert to bytes (x1,000,000) so the gauges
            # (renamed meraki_org_application_usage_*_bytes, issue #531) carry
            # base-unit values.
            total_mb = category_data.get("total", 0) * 1_000_000
            downstream_mb = category_data.get("downstream", 0) * 1_000_000
            upstream_mb = category_data.get("upstream", 0) * 1_000_000
            percentage = category_data.get("percentage", 0)

            # Set metrics
            # Create org labels using helper
            org_data = {"id": org_id, "name": org_name}
            labels = create_org_labels(
                org_data,
                category=sanitized_category,
            )

            if self._application_usage_total_mb:
                self._application_usage_total_mb.labels(**labels).set(total_mb)

            if self._application_usage_downstream_mb:
                self._application_usage_downstream_mb.labels(**labels).set(downstream_mb)

            if self._application_usage_upstream_mb:
                self._application_usage_upstream_mb.labels(**labels).set(upstream_mb)

            if self._application_usage_percentage:
                self._application_usage_percentage.labels(**labels).set(percentage)

        logger.debug(
            "Collected application usage metrics",
            org_id=org_id,
            categories_count=len(response),
        )

    # --- Phase 4 (#618) organization signal expansion ---

    @log_api_call("getOrganizationConfigTemplates")
    async def _fetch_config_templates(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch the organization's configuration templates.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            Configuration templates (empty list when none are defined).

        """
        self._track_api_call("getOrganizationConfigTemplates")
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationConfigTemplates,
            org_id,
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationConfigTemplates",
            ),
        )

    async def _collect_config_templates(self, org_id: str, org_name: str) -> None:
        """Collect config-template count and template-binding metrics (#297).

        Raises on a real API failure so the coordinator's per-org accounting
        counts it. An empty template list is normal (org has no templates).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        if not self._should_run_group(EndpointGroupName.ORG_CONFIG_TEMPLATES):
            return

        with LogContext(org_id=org_id, org_name=org_name):
            templates = await self._fetch_config_templates(org_id)
            # Zero extra API call: derive the bound-network count from the
            # already-cached, NetworkFilter-applied inventory networks.
            networks = await self.inventory.get_networks(org_id) if self.inventory else []

        self._mark_group_ran(EndpointGroupName.ORG_CONFIG_TEMPLATES)
        ttl = self._group_ttl_seconds(EndpointGroupName.ORG_CONFIG_TEMPLATES)

        bound_count = sum(1 for n in networks if n.get("isBoundToConfigTemplate"))
        labels = create_org_labels({"id": org_id, "name": org_name})
        self._set_metric(
            self._org_config_templates,
            labels,
            len(templates),
            OrgMetricName.ORG_CONFIG_TEMPLATES.value,
            ttl_seconds=ttl,
        )
        self._set_metric(
            self._org_networks_bound_to_template,
            labels,
            bound_count,
            OrgMetricName.ORG_NETWORKS_BOUND_TO_TEMPLATE.value,
            ttl_seconds=ttl,
        )
        logger.debug(
            "Collected config template metrics",
            org_id=org_id,
            template_count=len(templates),
            networks_bound=bound_count,
        )

    @log_api_call("getOrganizationAdaptivePolicyOverview")
    async def _fetch_adaptive_policy_overview(self, org_id: str) -> dict[str, Any]:
        """Fetch the organization's adaptive-policy aggregate statistics.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        dict[str, Any]
            Adaptive-policy overview (``counts`` object).

        """
        self._track_api_call("getOrganizationAdaptivePolicyOverview")
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationAdaptivePolicyOverview,
            org_id,
        )
        return cast(
            dict[str, Any],
            validate_response_format(
                response,
                expected_type=dict,
                operation="getOrganizationAdaptivePolicyOverview",
            ),
        )

    async def _collect_adaptive_policy(self, org_id: str, org_name: str) -> None:
        """Collect adaptive-policy overview counts (#298).

        Adaptive policy is absent unless the organization is licensed for it;
        the endpoint 404s (or 400s) otherwise, which is a benign soft-skip
        rather than a collection failure (mirrors the license.py pattern).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        if not self._should_run_group(EndpointGroupName.ORG_ADAPTIVE_POLICY):
            return

        try:
            with LogContext(org_id=org_id, org_name=org_name):
                overview = await self._fetch_adaptive_policy_overview(org_id)
        except Exception as e:
            if "404" in str(e) or "400" in str(e):
                logger.debug(
                    "Adaptive policy overview not available (org not licensed)",
                    org_id=org_id,
                    org_name=org_name,
                )
                return
            raise

        self._mark_group_ran(EndpointGroupName.ORG_ADAPTIVE_POLICY)
        ttl = self._group_ttl_seconds(EndpointGroupName.ORG_ADAPTIVE_POLICY)

        counts = overview.get("counts", {}) if isinstance(overview, dict) else {}
        labels = create_org_labels({"id": org_id, "name": org_name})
        self._set_metric(
            self._org_adaptive_policy_groups,
            labels,
            counts.get("groups") or 0,
            OrgMetricName.ORG_ADAPTIVE_POLICY_GROUPS.value,
            ttl_seconds=ttl,
        )
        self._set_metric(
            self._org_adaptive_policy_acls,
            labels,
            counts.get("customAcls") or 0,
            OrgMetricName.ORG_ADAPTIVE_POLICY_ACLS.value,
            ttl_seconds=ttl,
        )
        self._set_metric(
            self._org_adaptive_policy_policies,
            labels,
            counts.get("policies") or 0,
            OrgMetricName.ORG_ADAPTIVE_POLICY_POLICIES.value,
            ttl_seconds=ttl,
        )
        logger.debug(
            "Collected adaptive policy metrics",
            org_id=org_id,
            groups=counts.get("groups"),
            custom_acls=counts.get("customAcls"),
            policies=counts.get("policies"),
        )

    async def _collect_top_usage_metrics(self, org_id: str, org_name: str) -> bool:
        """Collect org-wide top-N usage metrics (#299).

        Returns the sub-collector's success/failure signal (see
        ``_collect_api_metrics``) so an isolated failure is counted by
        ``OrgHealthTracker`` (F-172).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        return await self.top_usage_collector.collect(org_id, org_name) is True

    async def _collect_webhook_logs_metrics(self, org_id: str, org_name: str) -> bool:
        """Collect webhook delivery-log metrics (#300).

        Returns the sub-collector's success/failure signal (see
        ``_collect_api_metrics``) so an isolated failure is counted by
        ``OrgHealthTracker`` (F-172).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        return await self.webhook_logs_collector.collect(org_id, org_name) is True

    async def _collect_firmware_compliance_metrics(self, org_id: str, org_name: str) -> bool:
        """Collect firmware compliance metrics (#611).

        Returns the sub-collector's success/failure signal (see
        ``_collect_api_metrics``) so an isolated failure is counted by
        ``OrgHealthTracker`` (F-172).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        return await self.firmware_collector.collect_compliance(org_id, org_name) is True
