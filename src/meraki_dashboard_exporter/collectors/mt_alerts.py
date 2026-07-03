"""Medium-tier MT sensor alerting metric collector.

This collector reports the count of currently-alerting MT sensors per
network per metric (e.g. temperature, humidity, door, water, co2, noise),
via the per-network `getNetworkSensorAlertsCurrentOverviewByMetric` endpoint.
Because this endpoint is per-network it is a dedicated, inventory-backed
collector (unlike the org-wide, inventory-free `MTSensorCollector`) so that
the configured `NetworkFilter` is enforced.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from ..core.async_utils import ManagedTaskGroup
from ..core.batch_processing import process_in_batches_with_errors
from ..core.collector import MetricCollector
from ..core.constants import MTMetricName, ProductType
from ..core.domain_models import SensorAlertsOverviewByMetric
from ..core.error_handling import (
    ErrorCategory,
    NothingCollectedError,
    validate_response_format,
    with_error_handling,
)
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call
from ..core.logging_helpers import LogContext, log_metric_collection_summary
from ..core.metrics import LabelName, create_labels
from ..core.registry import register_collector
from ..core.scheduler import EndpointGroup, EndpointGroupName

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager
    from ..core.org_health import OrgHealthTracker
    from ..services.inventory import OrganizationInventory

logger = get_logger(__name__)


class SensorRelatedDevice(BaseModel):
    """One related-device entry under ``relationships.livestream.relatedDevices`` (#308).

    ⚠ Phase-6 LIVE VERIFICATION: confirm the field names (``serial``,
    ``productType``) and the overall response shape of
    ``getNetworkSensorRelationships`` against the live API before freezing.
    ``extra="allow"`` keeps parsing forward-compatible until then. These
    models live here (not ``core/domain_models.py``) per the #618
    seam-funnelling convention - domain_models.py is a shared seam edited only
    during the integration/wiring pass (see ``mv.py``'s
    ``CameraAnalyticsRecentZone`` for the same precedent).
    """

    serial: str | None = None
    productType: str | None = None

    model_config = ConfigDict(extra="allow")


class SensorLivestreamRelationship(BaseModel):
    """The ``relationships.livestream`` object of a sensor-relationship entry."""

    relatedDevices: list[SensorRelatedDevice] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class SensorRelationshipSet(BaseModel):
    """The ``relationships`` object of a sensor-relationship entry."""

    livestream: SensorLivestreamRelationship | None = None

    model_config = ConfigDict(extra="allow")


class SensorRelationshipDeviceRef(BaseModel):
    """The ``device`` object of a sensor-relationship entry."""

    serial: str | None = None

    model_config = ConfigDict(extra="allow")


class SensorRelationshipEntry(BaseModel):
    """One row from ``getNetworkSensorRelationships`` (#308)."""

    device: SensorRelationshipDeviceRef | None = None
    relationships: SensorRelationshipSet | None = None

    model_config = ConfigDict(extra="allow")


@register_collector
class MTSensorAlertsCollector(MetricCollector):
    """Collector for network-wide currently-alerting MT sensor counts."""

    # #617 §2: per-sensor-network fetch (getNetworkSensorAlertsCurrentOverviewByMetric);
    # cost is one call per sensor-capable network.
    #
    # Phase 4 (#618): MT_ALERT_PROFILES (#302, getNetworkSensorAlertsProfiles)
    # and MT_RELATIONSHIPS (#308, getNetworkSensorRelationships) are two more
    # per-sensor-network fetches bundled into this same collector/tier; each
    # gates independently via its own scheduler group so they can stretch
    # apart from MT_SENSOR_ALERTS under adaptive budgeting.
    endpoint_groups: ClassVar[tuple[EndpointGroup, ...]] = (
        EndpointGroup(
            name=EndpointGroupName.MT_SENSOR_ALERTS,
            priority=2,
            floor_seconds=300,
            cost_fn=lambda shape: shape.sensor_network_count,
        ),
        EndpointGroup(
            name=EndpointGroupName.MT_ALERT_PROFILES,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda shape: float(shape.sensor_network_count),
        ),
        EndpointGroup(
            name=EndpointGroupName.MT_RELATIONSHIPS,
            priority=4,
            floor_seconds=900,
            cost_fn=lambda shape: float(shape.sensor_network_count),
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
        """Initialize MT sensor alerts collector."""
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

        # Shared per-org health tracker (F-169): when present, per-org collection is
        # skipped for organizations currently in backoff. Gating consumer only -- the
        # tracker is owned/updated by OrganizationCollector.
        self.org_health_tracker = org_health_tracker

    def _initialize_metrics(self) -> None:
        """Initialize sensor alerting metrics."""
        self._alerting_sensors_count = self._create_gauge(
            MTMetricName.MT_ALERTING_SENSORS_COUNT,
            "Count of currently-alerting MT sensors per network per metric",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.METRIC,
            ],
        )

        # Phase 4 (#302): configured sensor alert profile count per network.
        # An empty list ([]) is a legitimate value (0 configured profiles) -
        # it is emitted, not skipped; only a fetch error skips emission.
        self._alert_profiles_count = self._create_gauge(
            MTMetricName.MT_ALERT_PROFILES,
            "Count of configured MT sensor alert profiles per network",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
            ],
        )

        # Phase 4 (#308): MT sensor <-> related-device (e.g. MV camera)
        # relationship join carrier. One series per sensor->related-device link.
        self._related_device_info = self._create_gauge(
            MTMetricName.MT_RELATED_DEVICE_INFO,
            "MT sensor to related-device link info (1 = present)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SENSOR_SERIAL,
                LabelName.RELATED_SERIAL,
                LabelName.PRODUCT_TYPE,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect network-wide sensor alerting counts across all organizations."""
        start_time = asyncio.get_event_loop().time()
        organizations_processed = 0

        if not self.inventory:
            raise RuntimeError(
                "Inventory service not configured for MTSensorAlertsCollector. "
                "This is a programming error - collectors must be initialized with "
                "inventory service."
            )

        # #617 gate: skip the whole per-network fan-out only when NONE of this
        # collector's three groups (alerting counts, alert profiles, #308
        # MT<->related-device relationships) are due this heartbeat. Each
        # group's own due-ness is threaded down to the per-network fetch sites
        # so a group that stretched further under adaptive budgeting doesn't
        # get force-refreshed just because a sibling group is due.
        alerts_due = self._should_run_group(EndpointGroupName.MT_SENSOR_ALERTS)
        profiles_due = self._should_run_group(EndpointGroupName.MT_ALERT_PROFILES)
        relationships_due = self._should_run_group(EndpointGroupName.MT_RELATIONSHIPS)
        if not (alerts_due or profiles_due or relationships_due):
            logger.debug("No MT sensor alert-family groups due this heartbeat; skipping")
            return

        organizations = await self.inventory.get_organizations()
        if not organizations:
            logger.warning("No organizations found for MT sensor alerts collection")
            return

        # Backoff check moved into the coordinator's task-creation loop (#509 /
        # frozen rule 2c) so an all-orgs-in-backoff cycle can't masquerade as
        # success -- checked before constructing the worker coroutine to avoid
        # never-awaited-coroutine warnings.
        skipped_backoff = 0
        async with ManagedTaskGroup(
            name="mt_sensor_alerts_collector_orgs",
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
                        "Skipping MT sensor alert collection for organization in backoff",
                        org_id=org_id,
                        org_name=org_name,
                    )
                    continue
                await group.create_task(
                    self._collect_org_sensor_alerts(
                        org_id,
                        org_name,
                        alerts_due=alerts_due,
                        profiles_due=profiles_due,
                        relationships_due=relationships_due,
                    ),
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

        # Successful cycle: advance the scheduler's last-ran clock for each
        # group that was due this heartbeat.
        if alerts_due:
            self._mark_group_ran(EndpointGroupName.MT_SENSOR_ALERTS)
        if profiles_due:
            self._mark_group_ran(EndpointGroupName.MT_ALERT_PROFILES)
        if relationships_due:
            self._mark_group_ran(EndpointGroupName.MT_RELATIONSHIPS)

        log_metric_collection_summary(
            "MTSensorAlertsCollector",
            metrics_collected=0,
            duration_seconds=asyncio.get_event_loop().time() - start_time,
            organizations_processed=organizations_processed,
            api_calls_made=0,
        )

    @with_error_handling(
        operation="Collect organization MT sensor alerts",
        continue_on_error=False,
    )
    async def _collect_org_sensor_alerts(
        self,
        org_id: str,
        org_name: str | None = None,
        alerts_due: bool = True,
        profiles_due: bool = False,
        relationships_due: bool = False,
    ) -> None:
        """Collect sensor alerting counts for all sensor-capable networks in an organization.

        Note: the org-health-backoff gate has moved to ``_collect_impl`` (#509)
        so an all-orgs-in-backoff cycle is visible to the coordinator's failure
        accounting; this method no longer re-checks it.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str | None
            Organization name.
        alerts_due : bool
            Whether the ``MT_SENSOR_ALERTS`` group is due this heartbeat
            (defaults to ``True`` for direct/legacy callers).
        profiles_due : bool
            Whether the ``MT_ALERT_PROFILES`` group (#302) is due this
            heartbeat.
        relationships_due : bool
            Whether the ``MT_RELATIONSHIPS`` group (#308) is due this
            heartbeat.

        """
        if self.inventory is None:
            return

        with LogContext(org_id=org_id):
            networks = await self.inventory.get_networks(org_id)

        sensor_networks = [
            network for network in networks if ProductType.SENSOR in network.get("productTypes", [])
        ]
        if not sensor_networks:
            return

        for network in sensor_networks:
            network["orgId"] = org_id
            network["orgName"] = org_name or org_id

        async def _process_network(network: dict[str, Any]) -> None:
            if alerts_due:
                await self._collect_network_alerts(network)
            if profiles_due:
                await self._collect_network_alert_profiles(network)
            if relationships_due:
                await self._collect_network_relationships(network)

        await process_in_batches_with_errors(
            sensor_networks,
            _process_network,
            batch_size=self.settings.api.network_batch_size,
            delay_between_batches=self.settings.api.batch_delay,
            item_description="MT sensor alerts",
            error_context_func=lambda network: {
                "org_id": org_id,
                "org_name": org_name or org_id,
                "network_id": network.get("id"),
                "network_name": network.get("name"),
            },
        )

    async def _collect_network_alerts(self, network: dict[str, Any]) -> None:
        """Collect sensor alerting counts for a single network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data (stamped with `orgId`/`orgName` by the caller).

        """
        network_id = network.get("id", "")
        org_id = network.get("orgId", "")

        raw_overview = await self._fetch_network_alerts_overview(network_id)
        if raw_overview is None:
            return

        overview = SensorAlertsOverviewByMetric.model_validate(raw_overview)
        counts = overview.counts
        if not isinstance(counts, dict):
            return

        ttl_seconds = self._group_ttl_seconds(EndpointGroupName.MT_SENSOR_ALERTS)

        for metric_name, value in counts.items():
            numeric_value = self._normalize_count(value)
            if numeric_value is None:
                continue

            labels = create_labels(
                org_id=org_id,
                network_id=network_id,
                metric=metric_name,
            )
            self._set_metric(
                self._alerting_sensors_count,
                labels,
                numeric_value,
                MTMetricName.MT_ALERTING_SENSORS_COUNT.value,
                ttl_seconds=ttl_seconds,
            )

    async def _collect_network_alert_profiles(self, network: dict[str, Any]) -> None:
        """Collect the configured sensor alert profile count for a single network (#302).

        An empty list (``[]``) is the documented normal case for a network
        with no configured profiles and IS emitted as ``0`` - only a fetch
        error (``None`` from the ``@with_error_handling``-wrapped fetcher)
        skips emission.

        Parameters
        ----------
        network : dict[str, Any]
            Network data (stamped with `orgId`/`orgName` by the caller).

        """
        network_id = network.get("id", "")
        org_id = network.get("orgId", "")

        profiles = await self._fetch_network_alert_profiles(network_id)
        if profiles is None:
            return

        ttl_seconds = self._group_ttl_seconds(EndpointGroupName.MT_ALERT_PROFILES)
        labels = create_labels(org_id=org_id, network_id=network_id)
        self._set_metric(
            self._alert_profiles_count,
            labels,
            len(profiles),
            MTMetricName.MT_ALERT_PROFILES.value,
            ttl_seconds=ttl_seconds,
        )

    async def _collect_network_relationships(self, network: dict[str, Any]) -> None:
        """Collect MT sensor <-> related-device links for a single network (#308).

        Emits one ``meraki_mt_related_device_info`` series per
        sensor -> related-device link found under each entry's
        ``relationships.livestream.relatedDevices``.

        ⚠ Phase-6 LIVE VERIFICATION: the response shape (``device.serial`` +
        ``relationships.livestream.relatedDevices[{serial,productType}]``) has
        not been confirmed against a live network with MT<->MV pairings
        configured.

        Parameters
        ----------
        network : dict[str, Any]
            Network data (stamped with `orgId`/`orgName` by the caller).

        """
        network_id = network.get("id", "")
        org_id = network.get("orgId", "")

        raw_entries = await self._fetch_network_sensor_relationships(network_id)
        if raw_entries is None:
            return

        ttl_seconds = self._group_ttl_seconds(EndpointGroupName.MT_RELATIONSHIPS)

        for raw_entry in raw_entries:
            try:
                entry = SensorRelationshipEntry.model_validate(raw_entry)
            except Exception:
                logger.debug(
                    "Failed to parse sensor relationship entry",
                    network_id=network_id,
                )
                continue

            sensor_serial = entry.device.serial if entry.device else None
            if not sensor_serial:
                continue

            livestream = entry.relationships.livestream if entry.relationships else None
            related_devices = livestream.relatedDevices if livestream else []

            for related in related_devices:
                if not related.serial:
                    continue

                labels = create_labels(
                    org_id=org_id,
                    network_id=network_id,
                    sensor_serial=sensor_serial,
                    related_serial=related.serial,
                    product_type=related.productType or "",
                )
                self._set_metric(
                    self._related_device_info,
                    labels,
                    1,
                    MTMetricName.MT_RELATED_DEVICE_INFO.value,
                    ttl_seconds=ttl_seconds,
                )

    @staticmethod
    def _normalize_count(value: Any) -> int | None:
        """Normalize a `counts` entry to an int.

        Nested dicts (e.g. ``noise: {ambient: N}``) are summed across their
        integer leaf values; non-numeric/empty values are skipped.

        Parameters
        ----------
        value : Any
            Raw value from the API's `counts` mapping.

        Returns
        -------
        int | None
            Normalized count, or None if it could not be interpreted.

        """
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, dict):
            nested_total = 0
            found = False
            for nested_value in value.values():
                if isinstance(nested_value, bool):
                    continue
                if isinstance(nested_value, int):
                    nested_total += nested_value
                    found = True
            return nested_total if found else None
        return None

    @log_api_call("getNetworkSensorAlertsCurrentOverviewByMetric")
    @with_error_handling(
        operation="Fetch network sensor alerts overview",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_network_alerts_overview(self, network_id: str) -> dict[str, Any] | None:
        """Fetch the currently-alerting sensor overview for a network.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        dict[str, Any] | None
            The overview response (`supportedMetrics` + `counts`), or None on error.

        """
        if self.api is None:
            raise RuntimeError("API client not initialized")
        raw = await asyncio.to_thread(
            self.api.sensor.getNetworkSensorAlertsCurrentOverviewByMetric,
            network_id,
        )
        result = validate_response_format(
            raw, expected_type=dict, operation="getNetworkSensorAlertsCurrentOverviewByMetric"
        )
        return cast(dict[str, Any], result)

    @log_api_call("getNetworkSensorAlertsProfiles")
    @with_error_handling(
        operation="Fetch network sensor alert profiles",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_network_alert_profiles(self, network_id: str) -> list[dict[str, Any]] | None:
        """Fetch the configured sensor alert profiles for a network (#302).

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]] | None
            The list of configured alert profiles (empty list is a valid,
            emitted response), or None on error.

        """
        if self.api is None:
            raise RuntimeError("API client not initialized")
        raw = await asyncio.to_thread(
            self.api.sensor.getNetworkSensorAlertsProfiles,
            network_id,
        )
        result = validate_response_format(
            raw, expected_type=list, operation="getNetworkSensorAlertsProfiles"
        )
        return cast(list[dict[str, Any]], result)

    @log_api_call("getNetworkSensorRelationships")
    @with_error_handling(
        operation="Fetch network sensor relationships",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_network_sensor_relationships(
        self, network_id: str
    ) -> list[dict[str, Any]] | None:
        """Fetch MT sensor <-> related-device relationships for a network (#308).

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]] | None
            The raw list of sensor relationship entries, or None on error.

        """
        if self.api is None:
            raise RuntimeError("API client not initialized")
        raw = await asyncio.to_thread(
            self.api.sensor.getNetworkSensorRelationships,
            network_id,
        )
        result = validate_response_format(
            raw, expected_type=list, operation="getNetworkSensorRelationships"
        )
        return cast(list[dict[str, Any]], result)
