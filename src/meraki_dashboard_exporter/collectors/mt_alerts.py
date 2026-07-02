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
from typing import TYPE_CHECKING, Any, cast

from ..core.async_utils import ManagedTaskGroup
from ..core.batch_processing import process_in_batches_with_errors
from ..core.collector import MetricCollector
from ..core.constants import MTMetricName, ProductType, UpdateTier
from ..core.domain_models import SensorAlertsOverviewByMetric
from ..core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call
from ..core.logging_helpers import LogContext, log_metric_collection_summary
from ..core.metrics import LabelName, create_labels
from ..core.registry import register_collector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager
    from ..core.org_health import OrgHealthTracker
    from ..services.inventory import OrganizationInventory

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class MTSensorAlertsCollector(MetricCollector):
    """Collector for network-wide currently-alerting MT sensor counts."""

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
        """Initialize MT sensor alerts collector."""
        super().__init__(api, settings, registry, inventory, expiration_manager, rate_limiter)

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
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.METRIC,
            ],
        )

    @with_error_handling(
        operation="Collect MT sensor alerting metrics",
        continue_on_error=True,
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

        organizations = await self.inventory.get_organizations()
        if not organizations:
            logger.warning("No organizations found for MT sensor alerts collection")
            return

        async with ManagedTaskGroup(
            name="mt_sensor_alerts_collector_orgs",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for org in organizations:
                org_id = org["id"]
                org_name = org.get("name", org_id)
                await group.create_task(
                    self._collect_org_sensor_alerts(org_id, org_name),
                    name=f"org_{org_id}",
                )
                organizations_processed += 1

        log_metric_collection_summary(
            "MTSensorAlertsCollector",
            metrics_collected=0,
            duration_seconds=asyncio.get_event_loop().time() - start_time,
            organizations_processed=organizations_processed,
            api_calls_made=0,
        )

    @with_error_handling(
        operation="Collect organization MT sensor alerts",
        continue_on_error=True,
    )
    async def _collect_org_sensor_alerts(self, org_id: str, org_name: str | None = None) -> None:
        """Collect sensor alerting counts for all sensor-capable networks in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str | None
            Organization name.

        """
        if self.inventory is None:
            return

        # Skip organizations currently in backoff so a persistently-failing org
        # does not receive full-rate sensor-alert collection every cycle (F-169).
        if self.org_health_tracker is not None and not self.org_health_tracker.should_collect(
            org_id
        ):
            logger.debug(
                "Skipping MT sensor alert collection for organization in backoff",
                org_id=org_id,
                org_name=org_name or org_id,
            )
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

        await process_in_batches_with_errors(
            sensor_networks,
            self._collect_network_alerts,
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
        network_name = network.get("name", network_id)
        org_id = network.get("orgId", "")
        org_name = network.get("orgName", org_id)

        raw_overview = await self._fetch_network_alerts_overview(network_id)
        if raw_overview is None:
            return

        overview = SensorAlertsOverviewByMetric.model_validate(raw_overview)
        counts = overview.counts
        if not isinstance(counts, dict):
            return

        for metric_name, value in counts.items():
            numeric_value = self._normalize_count(value)
            if numeric_value is None:
                continue

            labels = create_labels(
                org_id=org_id,
                org_name=org_name,
                network_id=network_id,
                network_name=network_name,
                metric=metric_name,
            )
            self._set_metric(
                self._alerting_sensors_count,
                labels,
                numeric_value,
                MTMetricName.MT_ALERTING_SENSORS_COUNT.value,
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
