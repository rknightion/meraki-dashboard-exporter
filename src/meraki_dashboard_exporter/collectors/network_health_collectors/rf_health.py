"""RF Health collector for wireless network channel utilization metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ...core.constants import DeviceType, ProductType
from ...core.error_handling import validate_response_format
from ...core.label_helpers import create_device_labels, create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class RFHealthCollector(BaseNetworkHealthCollector):
    """Collector for wireless RF health metrics including channel utilization."""

    @staticmethod
    def _latest_bucket(buckets: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the most-recent utilization bucket for a radio.

        The API does not guarantee bucket ordering, so sort by end timestamp
        descending before picking the newest (F-017). The live legacy endpoint
        emits snake_case ``end_ts`` (evidence/live-api-verification.md Sample 1);
        the OpenAPI spec's ``endTime`` does NOT exist on the wire (#512). We read
        ``end_ts`` first and keep the ``endTime``/``endTs`` fallbacks defensively.
        Buckets with no timestamp sort last but preserve their original relative
        order, so a single-bucket response is unaffected.

        Parameters
        ----------
        buckets : list[dict[str, Any]]
            Non-empty list of per-interval utilization buckets for one radio.

        Returns
        -------
        dict[str, Any]
            The bucket with the latest end timestamp.

        """
        return sorted(
            buckets,
            key=lambda b: b.get("end_ts") or b.get("endTime") or b.get("endTs") or "",
            reverse=True,
        )[0]

    async def _fetch_organization_devices(
        self, org_id: str, network_id: str
    ) -> list[dict[str, Any]]:
        """Fetch devices for a network via the shared inventory cache.

        Uses the parent collector's inventory service so that the per-org
        device list is fetched at most once per cache TTL and reused across
        all networks in the org. Falls back to a direct API call only if
        inventory is unavailable.

        Parameters
        ----------
        org_id : str
            Organization ID.
        network_id : str
            Network ID to filter by.

        Returns
        -------
        list[dict[str, Any]]
            Devices belonging to ``network_id``.

        """
        inventory = self.parent.inventory

        if inventory is not None:
            # Served from the inventory cache — do NOT count it as an API call
            # (the cache accounts for its own real upstream calls); counting cache
            # hits here inflated the exporter's API-budget telemetry.
            return cast(
                list[dict[str, Any]],
                await inventory.get_devices(org_id, network_id=network_id),
            )

        # Fallback: real direct API call — this one is genuinely a request.
        self._track_api_call("getOrganizationDevices")
        devices = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevices,
            org_id,
            networkIds=[network_id],
            productTypes=[ProductType.WIRELESS],
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                devices, expected_type=list, operation="getOrganizationDevices"
            ),
        )

    @log_api_call("getNetworkNetworkHealthChannelUtilization")
    async def _fetch_channel_utilization(self, network_id: str) -> list[dict[str, Any]]:
        """Fetch channel utilization data.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]]
            Channel utilization data.

        """
        # Pin explicit query params (F-017). SDK 3.3.0 defaults for this endpoint are
        # timespan=1 day, resolution=600 (the only valid value), perPage=10 (range
        # 3-100). We only ever use the single most-recent bucket, so request the
        # shortest useful window (timespan=600 == one resolution=600 bucket) and the
        # largest page size to minimise pagination fan-out across a network's APs.
        response = await asyncio.to_thread(
            self.api.networks.getNetworkNetworkHealthChannelUtilization,
            network_id,
            timespan=600,
            resolution=600,
            perPage=100,
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getNetworkNetworkHealthChannelUtilization",
            ),
        )

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect RF health metrics for a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)
        org_id = network.get("orgId") or network.get("organizationId", "")
        org_name = network.get("orgName", org_id)

        try:
            with LogContext(network_id=network_id, network_name=network_name):
                # Get AP names for lookup using organization devices API
                if not org_id:
                    logger.warning("No organization ID in network data, cannot fetch devices")
                    device_names = {}
                else:
                    all_devices = await self._fetch_organization_devices(org_id, network_id)
                    # Filter for MR devices in this network
                    # Coalesce an explicit ``name: None`` (not just a missing
                    # key) to the serial so the AP name label is never None
                    # (F-019).
                    device_names = {
                        d["serial"]: d.get("name") or d["serial"]
                        for d in all_devices
                        if d.get("model", "").startswith(DeviceType.MR)
                        and d.get("networkId") == network_id
                    }

                channel_util = await self._fetch_channel_utilization(network_id)

            if channel_util:
                # Track network-wide averages
                network_2_4ghz_total = {"total": 0, "wifi": 0, "non_wifi": 0, "count": 0}
                network_5ghz_total = {"total": 0, "wifi": 0, "non_wifi": 0, "count": 0}

                for ap_data in channel_util:
                    serial = ap_data.get("serial", "")
                    model = ap_data.get("model", "")
                    name = device_names.get(serial, serial)

                    # Create device labels once per AP, before either radio block, so
                    # an AP that reports only wifi1 (5GHz) can't hit an UnboundLocalError
                    # on base_labels (F-017).
                    device_data = {
                        "serial": serial,
                        "name": name,
                        "model": model,
                        "networkId": network_id,
                        "networkName": network_name,
                    }
                    base_labels = create_device_labels(
                        device_data,
                        org_id=org_id,
                        org_name=org_name,
                    )

                    # Process 2.4GHz (wifi0)
                    if "wifi0" in ap_data and ap_data["wifi0"]:
                        latest_2_4 = self._latest_bucket(ap_data["wifi0"])
                        total_util = latest_2_4.get("utilization", 0)
                        wifi_util = latest_2_4.get("wifi", 0)
                        non_wifi_util = latest_2_4.get("non_wifi", 0)

                        # Set per-AP metrics for total utilization
                        labels = {**base_labels, "utilization_type": "total"}
                        self._set_metric_value(
                            "_ap_utilization_2_4ghz",
                            labels,
                            total_util,
                        )

                        # Set per-AP metrics for WiFi utilization
                        labels = {**base_labels, "utilization_type": "wifi"}
                        self._set_metric_value(
                            "_ap_utilization_2_4ghz",
                            labels,
                            wifi_util,
                        )

                        # Set per-AP metrics for non-WiFi utilization
                        labels = {**base_labels, "utilization_type": "non_wifi"}
                        self._set_metric_value(
                            "_ap_utilization_2_4ghz",
                            labels,
                            non_wifi_util,
                        )

                        # Update network totals
                        network_2_4ghz_total["total"] += total_util
                        network_2_4ghz_total["wifi"] += wifi_util
                        network_2_4ghz_total["non_wifi"] += non_wifi_util
                        network_2_4ghz_total["count"] += 1

                    # Process 5GHz (wifi1)
                    if "wifi1" in ap_data and ap_data["wifi1"]:
                        latest_5 = self._latest_bucket(ap_data["wifi1"])
                        total_util = latest_5.get("utilization", 0)
                        wifi_util = latest_5.get("wifi", 0)
                        non_wifi_util = latest_5.get("non_wifi", 0)

                        # Use same base labels as 2.4GHz
                        # Set per-AP metrics for total utilization
                        labels = {**base_labels, "utilization_type": "total"}
                        self._set_metric_value(
                            "_ap_utilization_5ghz",
                            labels,
                            total_util,
                        )

                        # Set per-AP metrics for WiFi utilization
                        labels = {**base_labels, "utilization_type": "wifi"}
                        self._set_metric_value(
                            "_ap_utilization_5ghz",
                            labels,
                            wifi_util,
                        )

                        # Set per-AP metrics for non-WiFi utilization
                        labels = {**base_labels, "utilization_type": "non_wifi"}
                        self._set_metric_value(
                            "_ap_utilization_5ghz",
                            labels,
                            non_wifi_util,
                        )

                        # Update network totals
                        network_5ghz_total["total"] += total_util
                        network_5ghz_total["wifi"] += wifi_util
                        network_5ghz_total["non_wifi"] += non_wifi_util
                        network_5ghz_total["count"] += 1

                # Calculate and set network-wide averages
                if network_2_4ghz_total["count"] > 0:
                    avg_total_2_4 = network_2_4ghz_total["total"] / network_2_4ghz_total["count"]
                    avg_wifi_2_4 = network_2_4ghz_total["wifi"] / network_2_4ghz_total["count"]
                    avg_non_wifi_2_4 = (
                        network_2_4ghz_total["non_wifi"] / network_2_4ghz_total["count"]
                    )

                    # Create network labels using helper
                    labels = create_network_labels(
                        network,
                        org_id=org_id,
                        org_name=org_name,
                        utilization_type="total",
                    )
                    self._set_metric_value(
                        "_network_utilization_2_4ghz",
                        labels,
                        avg_total_2_4,
                    )

                    labels = create_network_labels(
                        network,
                        org_id=org_id,
                        org_name=org_name,
                        utilization_type="wifi",
                    )
                    self._set_metric_value(
                        "_network_utilization_2_4ghz",
                        labels,
                        avg_wifi_2_4,
                    )

                    labels = create_network_labels(
                        network,
                        org_id=org_id,
                        org_name=org_name,
                        utilization_type="non_wifi",
                    )
                    self._set_metric_value(
                        "_network_utilization_2_4ghz",
                        labels,
                        avg_non_wifi_2_4,
                    )

                if network_5ghz_total["count"] > 0:
                    avg_total_5 = network_5ghz_total["total"] / network_5ghz_total["count"]
                    avg_wifi_5 = network_5ghz_total["wifi"] / network_5ghz_total["count"]
                    avg_non_wifi_5 = network_5ghz_total["non_wifi"] / network_5ghz_total["count"]

                    labels = create_network_labels(
                        network,
                        org_id=org_id,
                        org_name=org_name,
                        utilization_type="total",
                    )
                    self._set_metric_value(
                        "_network_utilization_5ghz",
                        labels,
                        avg_total_5,
                    )

                    labels = create_network_labels(
                        network,
                        org_id=org_id,
                        org_name=org_name,
                        utilization_type="wifi",
                    )
                    self._set_metric_value(
                        "_network_utilization_5ghz",
                        labels,
                        avg_wifi_5,
                    )

                    labels = create_network_labels(
                        network,
                        org_id=org_id,
                        org_name=org_name,
                        utilization_type="non_wifi",
                    )
                    self._set_metric_value(
                        "_network_utilization_5ghz",
                        labels,
                        avg_non_wifi_5,
                    )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            # or if the API exhausted retries on a rate limit (caught by
            # validate_response_format as RetryableAPIError).
            error_str = str(e)
            if (
                "400" in error_str
                or "404" in error_str
                or "Bad Request" in error_str
                or "rate limit" in error_str.lower()
            ):
                logger.debug(
                    "Channel utilization not available",
                    network_id=network_id,
                    network_name=network_name,
                    error=error_str,
                )
            else:
                logger.exception(
                    "Failed to collect RF health metrics",
                    network_id=network_id,
                    network_name=network_name,
                )
