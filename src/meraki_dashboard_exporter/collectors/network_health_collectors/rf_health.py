"""RF Health collector for wireless network channel utilization metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants import DeviceType, ProductType
from ...core.domain_models import RFHealthData
from ...core.logging import get_logger
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class RFHealthCollector(BaseNetworkHealthCollector):
    """Collector for wireless RF health metrics including channel utilization."""

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect RF health metrics for a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)
        org_id = network.get("organizationId")

        try:
            # Get channel utilization
            logger.debug(
                "Fetching channel utilization",
                network_id=network_id,
                network_name=network_name,
            )

            # Get AP names for lookup using organization devices API
            if not org_id:
                logger.warning(
                    "No organization ID in network data, cannot fetch devices",
                    network_id=network_id,
                )
                device_names = {}
            else:
                logger.debug(
                    "Fetching organization devices for RF health",
                    network_id=network_id,
                    org_id=org_id,
                )
                self._track_api_call("getOrganizationDevices")
                all_devices = await asyncio.to_thread(
                    self.api.organizations.getOrganizationDevices,
                    org_id,
                    networkIds=[network_id],
                    productTypes=[ProductType.WIRELESS],
                    total_pages="all",
                )
                logger.debug(
                    "Successfully fetched devices", network_id=network_id, count=len(all_devices)
                )
                # Filter for MR devices in this network
                device_names = {
                    d["serial"]: d.get("name", d["serial"])
                    for d in all_devices
                    if d.get("model", "").startswith(DeviceType.MR)
                    and d.get("networkId") == network_id
                }

            logger.debug("Fetching channel utilization data", network_id=network_id)
            self._track_api_call("getNetworkNetworkHealthChannelUtilization")
            channel_util = await asyncio.to_thread(
                self.api.networks.getNetworkNetworkHealthChannelUtilization,
                network_id,
                total_pages="all",
            )
            logger.debug(
                "Successfully fetched channel utilization",
                network_id=network_id,
                ap_count=len(channel_util) if channel_util else 0,
            )

            if channel_util:
                # Track network-wide averages
                network_2_4ghz_total = {"total": 0, "wifi": 0, "non_wifi": 0, "count": 0}
                network_5ghz_total = {"total": 0, "wifi": 0, "non_wifi": 0, "count": 0}

                for ap_data in channel_util:
                    serial = ap_data.get("serial", "")
                    model = ap_data.get("model", "")
                    name = device_names.get(serial, serial)

                    # Try to parse to domain model for validation
                    try:
                        RFHealthData(
                            serial=serial,
                            apName=name,
                            model=model,
                            band2_4GhzUtilization=ap_data.get("wifi0", [{}])[0].get("utilization")
                            if "wifi0" in ap_data and ap_data["wifi0"]
                            else None,
                            band5GhzUtilization=ap_data.get("wifi1", [{}])[0].get("utilization")
                            if "wifi1" in ap_data and ap_data["wifi1"]
                            else None,
                        )
                    except Exception:
                        logger.debug("Failed to parse RF data to domain model", serial=serial)

                    # Process 2.4GHz (wifi0)
                    if "wifi0" in ap_data and ap_data["wifi0"]:
                        latest_2_4 = ap_data["wifi0"][0]  # Get most recent data
                        total_util = latest_2_4.get("utilization", 0)
                        wifi_util = latest_2_4.get("wifi", 0)
                        non_wifi_util = latest_2_4.get("nonWifi", 0)

                        # Set per-AP metrics for total utilization
                        self._set_metric_value(
                            "_ap_utilization_2_4ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "total",
                            },
                            total_util,
                        )

                        # Set per-AP metrics for WiFi utilization
                        self._set_metric_value(
                            "_ap_utilization_2_4ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "wifi",
                            },
                            wifi_util,
                        )

                        # Set per-AP metrics for non-WiFi utilization
                        self._set_metric_value(
                            "_ap_utilization_2_4ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "non_wifi",
                            },
                            non_wifi_util,
                        )

                        # Update network totals
                        network_2_4ghz_total["total"] += total_util
                        network_2_4ghz_total["wifi"] += wifi_util
                        network_2_4ghz_total["non_wifi"] += non_wifi_util
                        network_2_4ghz_total["count"] += 1

                    # Process 5GHz (wifi1)
                    if "wifi1" in ap_data and ap_data["wifi1"]:
                        latest_5 = ap_data["wifi1"][0]  # Get most recent data
                        total_util = latest_5.get("utilization", 0)
                        wifi_util = latest_5.get("wifi", 0)
                        non_wifi_util = latest_5.get("nonWifi", 0)

                        # Set per-AP metrics for total utilization
                        self._set_metric_value(
                            "_ap_utilization_5ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "total",
                            },
                            total_util,
                        )

                        # Set per-AP metrics for WiFi utilization
                        self._set_metric_value(
                            "_ap_utilization_5ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "wifi",
                            },
                            wifi_util,
                        )

                        # Set per-AP metrics for non-WiFi utilization
                        self._set_metric_value(
                            "_ap_utilization_5ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "non_wifi",
                            },
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

                    self._set_metric_value(
                        "_network_utilization_2_4ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "total",
                        },
                        avg_total_2_4,
                    )

                    self._set_metric_value(
                        "_network_utilization_2_4ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "wifi",
                        },
                        avg_wifi_2_4,
                    )

                    self._set_metric_value(
                        "_network_utilization_2_4ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "non_wifi",
                        },
                        avg_non_wifi_2_4,
                    )

                if network_5ghz_total["count"] > 0:
                    avg_total_5 = network_5ghz_total["total"] / network_5ghz_total["count"]
                    avg_wifi_5 = network_5ghz_total["wifi"] / network_5ghz_total["count"]
                    avg_non_wifi_5 = network_5ghz_total["non_wifi"] / network_5ghz_total["count"]

                    self._set_metric_value(
                        "_network_utilization_5ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "total",
                        },
                        avg_total_5,
                    )

                    self._set_metric_value(
                        "_network_utilization_5ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "wifi",
                        },
                        avg_wifi_5,
                    )

                    self._set_metric_value(
                        "_network_utilization_5ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "non_wifi",
                        },
                        avg_non_wifi_5,
                    )

                logger.debug(
                    "Successfully collected RF health metrics",
                    network_id=network_id,
                    network_name=network_name,
                    ap_2_4ghz_count=network_2_4ghz_total["count"],
                    ap_5ghz_count=network_5ghz_total["count"],
                )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            error_str = str(e)
            if "400" in error_str or "404" in error_str or "Bad Request" in error_str:
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
