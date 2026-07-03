"""RF Health collector for wireless channel utilization metrics.

#271: this collector now reads channel utilization from the two org-wide
endpoints (``getOrganizationWirelessDevicesChannelUtilizationByDevice`` and
``…ByNetwork``) exactly once per collection cycle, instead of the per-network
``getNetworkNetworkHealthChannelUtilization`` call it used before. At scale this
collapses ``W`` per-network calls into two paginated org passes — the load
reduction the adaptive scheduler epic (#617) depends on. The collector is
therefore org-scoped: the coordinator calls :meth:`collect_org` once per org,
gated on the ``nh_channel_utilization`` endpoint group, rather than invoking a
per-network ``collect`` in the fan-out bundle.

⚠ Phase-6 LIVE VERIFICATION (do before freezing): the ``byBand`` response shape
here is coded against the OpenAPI spec. Unverified on the wire:
- the exact ``band`` string values (spec example shows ``"5"``; assumed
  ``"2.4"``/``"5"``/``"6"``);
- the ``wifi`` / ``nonWifi`` / ``total`` sub-object camelCase key names and the
  ``percentage`` field (the legacy per-network endpoint used snake_case
  ``non_wifi`` — the org-wide one is spec'd camelCase ``nonWifi``);
- 6GHz handling: there is no 6GHz gauge today, so ``band == "6"`` rows are
  currently dropped (whether to add a 6GHz series is a Phase-6 decision).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ...core.error_handling import validate_response_format
from ...core.label_helpers import create_device_labels, create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.scheduler import EndpointGroupName
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# ⚠ Phase-6: exact `band` string values on the wire.
_BAND_2_4 = "2.4"
_BAND_5 = "5"

# (metric utilization_type label value, API sub-object key). ⚠ Phase-6: the
# `nonWifi` camelCase key + `percentage` field.
_UTIL_KEYS: tuple[tuple[str, str], ...] = (
    ("total", "total"),
    ("wifi", "wifi"),
    ("non_wifi", "nonWifi"),
)


class RFHealthCollector(BaseNetworkHealthCollector):
    """Collector for org-wide wireless RF channel utilization (#271)."""

    async def _device_model_map(self, org_id: str) -> dict[str, str]:
        """Build a ``serial -> model`` map from the shared inventory cache.

        The org-wide byDevice response carries ``serial``/``mac``/``network.id``
        but no ``model``; the per-AP metric still labels by ``model``/
        ``device_type`` (#534-retained), so resolve those from inventory. Served
        from cache — not counted as an API call. Returns an empty map when
        inventory is unavailable (the per-AP labels then degrade to empty model).

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        dict[str, str]
            Mapping of device serial to model.

        """
        inventory = self.parent.inventory
        if inventory is None:
            return {}
        devices = await inventory.get_devices(org_id)
        return {d["serial"]: d.get("model", "") for d in devices if d.get("serial")}

    @log_api_call("getOrganizationWirelessDevicesChannelUtilizationByDevice")
    async def _fetch_channel_utilization_by_device(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch per-AP channel utilization for the whole org (paginated).

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            Per-device utilization rows (``serial``, ``network``, ``byBand``).

        """
        response = await asyncio.to_thread(
            self.api.wireless.getOrganizationWirelessDevicesChannelUtilizationByDevice,
            org_id,
            timespan=600,
            interval=600,
            perPage=1000,
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationWirelessDevicesChannelUtilizationByDevice",
            ),
        )

    @log_api_call("getOrganizationWirelessDevicesChannelUtilizationByNetwork")
    async def _fetch_channel_utilization_by_network(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch per-network channel utilization for the whole org (paginated).

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            Per-network utilization rows (``network``, ``byBand``).

        """
        response = await asyncio.to_thread(
            self.api.wireless.getOrganizationWirelessDevicesChannelUtilizationByNetwork,
            org_id,
            timespan=600,
            interval=600,
            perPage=1000,
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationWirelessDevicesChannelUtilizationByNetwork",
            ),
        )

    @staticmethod
    def _gauge_for_band(band: str, gauge_2_4: str, gauge_5: str) -> str | None:
        """Return the gauge attr name for a band string, or None to drop it.

        6GHz (``band == "6"``) and unknown bands are dropped — there is no 6GHz
        gauge today (⚠ Phase-6).
        """
        if band == _BAND_2_4:
            return gauge_2_4
        if band == _BAND_5:
            return gauge_5
        return None

    def _emit_bands(
        self,
        by_band: list[dict[str, Any]] | None,
        labels_base: dict[str, str],
        gauge_2_4: str,
        gauge_5: str,
        ttl_seconds: float | None,
    ) -> None:
        """Emit total/wifi/non_wifi utilization for each band in a ``byBand`` list."""
        for band_entry in by_band or []:
            band = str(band_entry.get("band", ""))
            gauge = self._gauge_for_band(band, gauge_2_4, gauge_5)
            if gauge is None:
                continue
            for util_label, api_key in _UTIL_KEYS:
                obj = band_entry.get(api_key) or {}
                pct = obj.get("percentage")
                if pct is None:
                    continue
                labels = {**labels_base, "utilization_type": util_label}
                self._set_metric_value(gauge, labels, pct, ttl_seconds=ttl_seconds)

    async def collect_org(
        self, org_id: str, org_name: str, networks: list[dict[str, Any]]
    ) -> bool:
        """Collect org-wide channel utilization and emit per-AP + per-network gauges.

        Called once per org per cycle by the coordinator (gated on
        ``nh_channel_utilization``). Rows referencing networks outside the
        supplied (already NetworkFilter- and wireless-filtered) ``networks`` set
        are dropped so the org-wide response respects the configured filter.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name (labels/logging).
        networks : list[dict[str, Any]]
            The org's filtered wireless networks. Used both as the allow-list
            for org-wide rows and to source per-network label data.

        Returns
        -------
        bool
            ``True`` if the org-wide channel-utilization fetch succeeded this
            cycle (a successful fetch returning empty still counts), ``False``
            on total failure (both org endpoints failed / an error was
            swallowed). The coordinator uses this to decide whether to mark the
            ``nh_channel_utilization`` group ran (#629): a total failure leaves
            the gate open so the next cycle retries.

        """
        if not org_id:
            logger.warning("No organization ID for channel utilization collection")
            return False

        allowed_ids = {n.get("id") for n in networks if n.get("id")}
        network_by_id = {n.get("id"): n for n in networks if n.get("id")}
        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.NH_CHANNEL_UTILIZATION)

        try:
            with LogContext(org_id=org_id):
                model_map = await self._device_model_map(org_id)
                by_device = await self._fetch_channel_utilization_by_device(org_id)
                by_network = await self._fetch_channel_utilization_by_network(org_id)

            # Per-AP utilization (byDevice).
            for row in by_device:
                network_id = (row.get("network") or {}).get("id", "")
                if network_id not in allowed_ids:
                    continue
                serial = row.get("serial", "")
                device_data = {
                    "serial": serial,
                    "model": model_map.get(serial, ""),
                    "networkId": network_id,
                }
                base_labels = create_device_labels(device_data, org_id=org_id, org_name=org_name)
                self._emit_bands(
                    row.get("byBand"),
                    base_labels,
                    "_ap_utilization_2_4ghz",
                    "_ap_utilization_5ghz",
                    ttl_seconds,
                )

            # Per-network average utilization (byNetwork).
            for row in by_network:
                network_id = (row.get("network") or {}).get("id", "")
                if network_id not in allowed_ids:
                    continue
                network = network_by_id.get(network_id) or {"id": network_id}
                base_labels = create_network_labels(network, org_id=org_id, org_name=org_name)
                self._emit_bands(
                    row.get("byBand"),
                    base_labels,
                    "_network_utilization_2_4ghz",
                    "_network_utilization_5ghz",
                    ttl_seconds,
                )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors) or
            # if the API exhausted retries on a rate limit (surfaced by
            # validate_response_format as RetryableAPIError). Swallow so a
            # channel-util failure does not fail the whole org's health verdict.
            error_str = str(e)
            if (
                "400" in error_str
                or "404" in error_str
                or "Bad Request" in error_str
                or "rate limit" in error_str.lower()
            ):
                logger.debug(
                    "Channel utilization not available",
                    org_id=org_id,
                    error=error_str,
                )
            else:
                logger.exception(
                    "Failed to collect RF health channel utilization",
                    org_id=org_id,
                )
            # Total failure this cycle: the coordinator must leave the
            # nh_channel_utilization gate open so the next cycle retries (#629).
            return False

        # Both org endpoints fetched (empty responses still count as success).
        return True
