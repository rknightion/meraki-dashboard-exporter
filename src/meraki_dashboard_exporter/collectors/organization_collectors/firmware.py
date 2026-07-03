"""Firmware upgrade collector for organization firmware metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels, create_org_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.scheduler import EndpointGroupName
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    from ..organization import OrganizationCollector

logger = get_logger(__name__)

# Statuses considered "pending"/in-flight for the pending-total gauge. The Meraki API
# returns capitalized status values (e.g. "Completed", "Cancelled"; scheduled/in-flight
# events use capitalized forms too), so membership is checked against the lower-cased
# status rather than the raw (label) value.
_PENDING_STATUSES = frozenset({"scheduled", "pending", "started"})

# By-device upgrade statuses that mean the device still has an outstanding
# (pending / in-progress / staged) firmware upgrade — used to derive per-network
# firmware compliance (#611). Compared case-insensitively.
# ⚠ Phase-6 live verification: confirm the getOrganizationFirmwareUpgradesByDevice
# upgrade-status field name and its exact value vocabulary.
_BY_DEVICE_PENDING_STATUSES = frozenset({
    "scheduled",
    "pending",
    "started",
    "in_progress",
    "in progress",
    "staged",
})


class FirmwareCollector(BaseOrganizationCollector):
    """Collector for organization firmware upgrade metrics."""

    def __init__(self, parent: OrganizationCollector) -> None:
        """Initialize the firmware collector.

        Parameters
        ----------
        parent : OrganizationCollector
            Parent OrganizationCollector instance that has metrics defined.

        """
        super().__init__(parent)
        # Bounded label combos emitted on a previous cycle, per org - used to zero out
        # combos that are absent this cycle instead of leaving a stale non-zero value.
        self._seen_upgrade_keys: dict[str, set[tuple[str, str]]] = {}
        self._seen_pending_product_types: dict[str, set[str]] = {}

    @log_api_call("getOrganizationFirmwareUpgrades")
    async def _fetch_firmware_upgrades(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch organization firmware upgrades.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of firmware upgrade events.

        """
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationFirmwareUpgrades,
            org_id,
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationFirmwareUpgrades",
            ),
        )

    @with_error_handling(
        operation="Collect firmware upgrade metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str) -> bool:
        """Collect firmware upgrade metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        Returns
        -------
        bool
            ``True`` on success or when the endpoint is unavailable for this
            org (404). On a real (non-404) failure the error is re-raised so
            the ``with_error_handling`` decorator can retry rate limits and
            then swallow it (returning ``None``); the parent coordinator treats
            any non-``True`` result as a failure so it is counted by
            ``OrgHealthTracker`` (F-172).

        """
        if not self.parent._should_run_group(EndpointGroupName.ORG_FIRMWARE):
            return True

        try:
            with LogContext(org_id=org_id, org_name=org_name):
                upgrades = await self._fetch_firmware_upgrades(org_id)
                allowed_network_ids = (
                    await self.inventory.get_allowed_network_ids(org_id)
                    if self.inventory is not None
                    else None
                )

            # Fetch succeeded — record the group ran so gating stretches.
            self.parent._mark_group_ran(EndpointGroupName.ORG_FIRMWARE)

            if not upgrades:
                logger.debug("No firmware upgrade events available", org_id=org_id)

            # Always process (even with an empty list) so bounded label combos that
            # disappear this cycle get explicitly zeroed rather than left stale.
            self._process_firmware_upgrades(org_id, org_name, upgrades, allowed_network_ids)
            return True

        except Exception as e:
            if "404" in str(e):
                logger.debug(
                    "No firmware upgrade information available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
                return True
            raise  # Let decorator handle non-404 errors (retry + swallow)

    def _process_firmware_upgrades(
        self,
        org_id: str,
        org_name: str,
        upgrades: list[dict[str, Any]],
        allowed_network_ids: set[str] | None,
    ) -> None:
        """Process firmware upgrade events into aggregated metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        upgrades : list[dict[str, Any]]
            List of firmware upgrade events.
        allowed_network_ids : set[str] | None
            Network IDs permitted by the configured NetworkFilter, or None when
            filtering is disabled (accept every row).

        """
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.ORG_FIRMWARE)

        # Aggregate counts by (product_type, status) - bound cardinality, never per-network/device.
        upgrade_counts: dict[tuple[str, str], int] = {}
        pending_counts: dict[str, int] = {}
        skipped = 0

        for event in upgrades:
            network_id = event.get("network", {}).get("id")
            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            product_type = event.get("productTypes", "unknown")
            status = event.get("status", "unknown")

            key = (product_type, status)
            upgrade_counts[key] = upgrade_counts.get(key, 0) + 1

            # The API returns capitalized status values (e.g. "Completed"); compare
            # case-insensitively so the pending gauge actually fires.
            status_normalized = status.lower() if isinstance(status, str) else status
            if status_normalized in _PENDING_STATUSES:
                pending_counts[product_type] = pending_counts.get(product_type, 0) + 1

        org_data = {"id": org_id, "name": org_name}

        # Zero out combos that were emitted on a previous cycle but are absent this
        # cycle, so a status that stops recurring (e.g. all upgrades finish) reports 0
        # rather than freezing at its last non-zero value.
        seen_upgrade_keys = self._seen_upgrade_keys.setdefault(org_id, set())
        for stale_product_type, stale_status in seen_upgrade_keys - upgrade_counts.keys():
            labels = create_org_labels(
                org_data,
                product_type=stale_product_type,
                status=stale_status,
            )
            self._set_metric_value("_org_firmware_upgrades_total", labels, 0, ttl_seconds=ttl)

        for (product_type, status), count in upgrade_counts.items():
            labels = create_org_labels(
                org_data,
                product_type=product_type,
                status=status,
            )
            self._set_metric_value(
                "_org_firmware_upgrades_total",
                labels,
                count,
                ttl_seconds=ttl,
            )
        seen_upgrade_keys.clear()
        seen_upgrade_keys.update(upgrade_counts.keys())

        seen_pending_product_types = self._seen_pending_product_types.setdefault(org_id, set())
        for stale_product_type in seen_pending_product_types - pending_counts.keys():
            labels = create_org_labels(
                org_data,
                product_type=stale_product_type,
            )
            self._set_metric_value(
                "_org_firmware_upgrades_pending_total", labels, 0, ttl_seconds=ttl
            )

        for product_type, count in pending_counts.items():
            labels = create_org_labels(
                org_data,
                product_type=product_type,
            )
            self._set_metric_value(
                "_org_firmware_upgrades_pending_total",
                labels,
                count,
                ttl_seconds=ttl,
            )
        seen_pending_product_types.clear()
        seen_pending_product_types.update(pending_counts.keys())

        logger.info(
            "Collected firmware upgrade metrics",
            org_id=org_id,
            org_name=org_name,
            total_events=len(upgrades),
            pending_product_types=len(pending_counts),
            skipped_filtered_network=skipped,
        )

    # --- Firmware compliance (#611) ---

    @log_api_call("getOrganizationFirmwareUpgradesByDevice")
    async def _fetch_firmware_upgrades_by_device(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch per-device firmware upgrade status.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            Per-device firmware upgrade status entries.

        """
        self._track_api_call("getOrganizationFirmwareUpgradesByDevice")
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationFirmwareUpgradesByDevice,
            org_id,
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationFirmwareUpgradesByDevice",
            ),
        )

    @with_error_handling(
        operation="Collect firmware compliance metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_compliance(self, org_id: str, org_name: str) -> bool:
        """Collect firmware compliance metrics (#611).

        Emits two things:

        * ``meraki_device_firmware_info`` — a per-device join carrier (value 1)
          built entirely from the **cached inventory** (zero extra API calls),
          refreshed every cycle so serials join to their running firmware.
        * ``meraki_network_firmware_up_to_date`` — a per-network 1/0 gauge
          derived from ``getOrganizationFirmwareUpgradesByDevice`` (gated by the
          ORG_FIRMWARE_COMPLIANCE group).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        Returns
        -------
        bool
            ``True`` on success or when the by-device endpoint is unavailable
            for this org (404); on a real failure the error is re-raised so the
            decorator can retry then swallow it. The coordinator treats any
            non-``True`` result as a failure (F-172).

        """
        try:
            # Device firmware info rides cached inventory (zero API cost) and is
            # emitted every cycle, independent of the by-device group gate.
            await self._emit_device_firmware_info(org_id, org_name)

            # Per-network up-to-date derives from the by-device endpoint (gated).
            if not self.parent._should_run_group(EndpointGroupName.ORG_FIRMWARE_COMPLIANCE):
                return True

            with LogContext(org_id=org_id, org_name=org_name):
                by_device = await self._fetch_firmware_upgrades_by_device(org_id)
                allowed_network_ids = (
                    await self.inventory.get_allowed_network_ids(org_id)
                    if self.inventory is not None
                    else None
                )

            self.parent._mark_group_ran(EndpointGroupName.ORG_FIRMWARE_COMPLIANCE)
            self._process_firmware_compliance(org_id, org_name, by_device, allowed_network_ids)
            return True

        except Exception as e:
            if "404" in str(e):
                logger.debug(
                    "Firmware compliance information not available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
                return True
            raise  # Let decorator handle non-404 errors (retry + swallow)

    async def _emit_device_firmware_info(self, org_id: str, org_name: str) -> None:
        """Emit the per-device firmware info join carrier from cached inventory.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        if self.inventory is None:
            return

        devices = await self.inventory.get_devices(org_id)
        for device in devices:
            serial = device.get("serial")
            if not serial:
                continue
            labels = create_device_labels(
                device,
                org_id=org_id,
                firmware=device.get("firmware", ""),
            )
            # value 1: this is a name/attribute join carrier, joined on serial.
            self._set_metric_value("_device_firmware_info", labels, 1)

    @staticmethod
    def _is_device_pending(status: Any) -> bool:
        """Whether a by-device upgrade status indicates an outstanding upgrade."""
        if not isinstance(status, str):
            return False
        return status.lower() in _BY_DEVICE_PENDING_STATUSES

    def _process_firmware_compliance(
        self,
        org_id: str,
        org_name: str,
        by_device: list[dict[str, Any]],
        allowed_network_ids: set[str] | None,
    ) -> None:
        """Derive per-network firmware up-to-date state from by-device statuses.

        A network reports ``1`` when none of its devices have an outstanding
        (pending/in-progress/staged) upgrade, ``0`` when at least one does.
        Networks outside the configured NetworkFilter are skipped.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        by_device : list[dict[str, Any]]
            Per-device firmware upgrade status entries.
        allowed_network_ids : set[str] | None
            Network IDs permitted by the NetworkFilter, or None (accept all).

        """
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.ORG_FIRMWARE_COMPLIANCE)

        # network_id -> whether any device on it still has a pending upgrade.
        net_pending: dict[str, bool] = {}
        skipped = 0
        for entry in by_device:
            network_id = (entry.get("network") or {}).get("id")
            if not network_id:
                continue
            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue
            # ⚠ Phase-6: the upgrade status may live under `upgrade.status` or a
            # top-level `status`; handle both leniently.
            upgrade = entry.get("upgrade")
            status = upgrade.get("status") if isinstance(upgrade, dict) else None
            if status is None:
                status = entry.get("status")
            pending = self._is_device_pending(status)
            net_pending[network_id] = net_pending.get(network_id, False) or pending

        org_data = {"id": org_id, "name": org_name}
        for network_id, pending in net_pending.items():
            labels = create_org_labels(org_data, network_id=network_id)
            self._set_metric_value(
                "_network_firmware_up_to_date",
                labels,
                0 if pending else 1,
                ttl_seconds=ttl,
            )

        logger.info(
            "Collected firmware compliance metrics",
            org_id=org_id,
            org_name=org_name,
            networks_evaluated=len(net_pending),
            skipped_filtered_network=skipped,
        )
