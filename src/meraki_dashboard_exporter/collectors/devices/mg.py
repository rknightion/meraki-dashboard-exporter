"""MG cellular gateway collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from ...core.constants import MGMetricName
from ...core.domain_models import CellularGatewayUplinkStatus
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName, create_labels
from ...core.scheduler import EndpointGroupName
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    from ..device import DeviceCollector

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# #304 — Cellular band config + serving cell (Phase 4, spec-only)
#
# ⚠ No MG hardware is available to confirm the live response shape for either
# endpoint below; the OpenAPI spec is known to be wrong for some Meraki
# endpoints (see evidence/live-api-verification.md). These models and the
# parsing helpers that follow are deliberately lenient/defensive about the
# exact nesting so an unexpected shape degrades to "no metric emitted" rather
# than raising. MUST be re-verified against a live response in Phase 6.
# ---------------------------------------------------------------------------


class MGCellularBandsDevice(BaseModel):
    """Per-device cellular band-configuration row.

    Source: ``getOrganizationDevicesCellularUplinksBandsByDevice``. The
    ``bands`` sub-structure is kept as a loosely-typed ``dict`` rather than
    modeled field-by-field (its nesting is unverified) and parsed defensively
    by ``_count_bands_by_slot`` in the collector.
    """

    __meraki_op__ = "getOrganizationDevicesCellularUplinksBandsByDevice"

    serial: str = ""
    model: str | None = None
    network: dict[str, Any] | None = None
    networkId: str | None = None
    bands: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    def resolved_network_id(self) -> str | None:
        """Resolve the network ID.

        Tries a flat ``networkId`` field first, then falls back to a nested
        ``network.id`` (both shapes are plausible; unverified).
        """
        if self.networkId:
            return self.networkId
        if isinstance(self.network, dict):
            nid = self.network.get("id")
            if isinstance(nid, str):
                return nid
        return None


class MGCellularTowersDevice(BaseModel):
    """Per-device serving-cell-tower row.

    Source: ``getOrganizationDevicesCellularUplinksTowersByDevice``. ``towers``
    entries are kept as loosely-typed dicts and picked over defensively by
    ``_extract_serving_cell`` since the exact field names (``cellId`` vs
    ``id`` vs ``servingCellId``, ``tac`` vs ``trackingAreaCode``) are
    unverified.
    """

    __meraki_op__ = "getOrganizationDevicesCellularUplinksTowersByDevice"

    serial: str = ""
    model: str | None = None
    network: dict[str, Any] | None = None
    networkId: str | None = None
    towers: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")

    def resolved_network_id(self) -> str | None:
        """Resolve the network ID.

        Tries a flat ``networkId`` field first, then falls back to a nested
        ``network.id`` (both shapes are plausible; unverified).
        """
        if self.networkId:
            return self.networkId
        if isinstance(self.network, dict):
            nid = self.network.get("id")
            if isinstance(nid, str):
                return nid
        return None


# Bounded label vocabularies (frozen spec, #618 Phase 4 seam) - anything
# outside these sets is dropped/normalized rather than emitted verbatim, so a
# malformed or attacker-influenced API response can never grow cardinality.
_KNOWN_SLOTS = frozenset({"sim1", "sim2", "sim3"})
_KNOWN_STATUSES = frozenset({"enabled", "masked", "supported"})

# #328: bounded HA role vocabulary per the OpenAPI spec ("for devices that do
# not support HA, this will be 'primary'"). Anything else is dropped rather
# than emitted, so an unexpected API value can never grow label cardinality.
_KNOWN_HA_ROLES = frozenset({"primary", "spare"})

# Recognized radio-access-technology spellings, normalized to the frozen
# CONNECTION_TYPE label vocabulary. Anything unrecognized collapses to "other".
_RAT_ALIASES: dict[str, str] = {
    "lte": "lte",
    "4g": "lte",
    "5gnsa": "5gNsa",
    "5gsa": "5gSa",
    "5g": "5gNsa",  # ambiguous bare "5G" - most common early NSA deployment
}


def _normalize_connection_type(value: Any) -> str:
    """Map a raw RAT string to the bounded CONNECTION_TYPE label vocabulary.

    Parameters
    ----------
    value : Any
        Raw radio-access-technology value from the API (e.g. "LTE", "5G-NSA").

    Returns
    -------
    str
        One of "lte", "5gNsa", "5gSa", or "other" for anything unrecognized
        (including missing/non-string values) - never the raw input, so an
        unexpected string can't grow label cardinality.

    """
    if not isinstance(value, str) or not value:
        return "other"
    normalized = value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    return _RAT_ALIASES.get(normalized, "other")


def _looks_like_status_bucket(candidate: dict[str, Any]) -> bool:
    """Heuristic check for whether ``candidate``'s keys look like status names.

    Used to disambiguate whether a per-slot dict is already keyed by status
    (``{"enabled": [...], "masked": [...]}``, no RAT breakdown) versus keyed
    by RAT with a nested status dict (``{"lte": {"enabled": [...]}}``).
    """
    return any(key in _KNOWN_STATUSES for key in candidate)


def _count_bands_by_slot(bands: dict[str, Any]) -> dict[tuple[str, str, str], int]:
    """Count cellular bands per (slot, connection_type, status).

    Handles two plausible response shapes defensively (the live shape is
    unverified - #304 is spec-only, no MG hardware available):

    1. RAT-nested: ``{"sim1": {"lte": {"enabled": [...], "masked": [...]}}}``
    2. Flat list of entries: ``{"sim1": [{"connectionType"/"type": ...,
       "status": ...}, ...]}``

    A bare status-keyed dict with no RAT breakdown (``{"sim1": {"enabled":
    [...]}}``) is also handled, bucketed under connection_type "other".
    Unrecognized slot keys, status values, and malformed entries are silently
    skipped rather than raising - this must never crash the collection loop
    over an unexpected shape.

    Parameters
    ----------
    bands : dict[str, Any]
        The raw ``bands`` sub-object from a single device's row.

    Returns
    -------
    dict[tuple[str, str, str], int]
        Mapping of (slot, connection_type, status) -> band count.

    """
    counts: dict[tuple[str, str, str], int] = {}
    if not isinstance(bands, dict):
        return counts

    for slot, slot_data in bands.items():
        if slot not in _KNOWN_SLOTS:
            continue

        if isinstance(slot_data, dict):
            if _looks_like_status_bucket(slot_data):
                for status, band_list in slot_data.items():
                    if status not in _KNOWN_STATUSES or not isinstance(band_list, list):
                        continue
                    key = (slot, "other", status)
                    counts[key] = counts.get(key, 0) + len(band_list)
            else:
                for rat, status_buckets in slot_data.items():
                    if not isinstance(status_buckets, dict):
                        continue
                    connection_type = _normalize_connection_type(rat)
                    for status, band_list in status_buckets.items():
                        if status not in _KNOWN_STATUSES or not isinstance(band_list, list):
                            continue
                        key = (slot, connection_type, status)
                        counts[key] = counts.get(key, 0) + len(band_list)
        elif isinstance(slot_data, list):
            for entry in slot_data:
                if not isinstance(entry, dict):
                    continue
                status = entry.get("status")
                if status not in _KNOWN_STATUSES:
                    continue
                rat = entry.get("connectionType") or entry.get("type") or entry.get("rat")
                connection_type = _normalize_connection_type(rat)
                key = (slot, connection_type, status)
                counts[key] = counts.get(key, 0) + 1

    return counts


def _extract_serving_cell(towers: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Pick the current serving cell (cell_id, tac) from a towers list.

    Defensive across plausible key names (``cellId``/``id``/``servingCellId``
    for the cell ID; ``tac``/``trackingAreaCode`` for the tracking area code)
    since the response shape is unverified (#304 is spec-only). Prefers an
    entry explicitly flagged ``serving``/``isServing`` if present, else the
    first entry carrying a usable ID.

    Parameters
    ----------
    towers : list[dict[str, Any]]
        Raw ``towers`` entries for one device.

    Returns
    -------
    tuple[str, str] | None
        ``(cell_id, tac)`` if a usable ID was found, else ``None`` (no
        metric should be emitted).

    """

    def _pick(entry: dict[str, Any]) -> tuple[str, str] | None:
        cell_id = (
            entry.get("cellId") or entry.get("id") or entry.get("servingCellId") or entry.get("cid")
        )
        if cell_id is None:
            return None
        tac = entry.get("tac") or entry.get("trackingAreaCode") or ""
        return str(cell_id), str(tac)

    for entry in towers:
        if isinstance(entry, dict) and (
            entry.get("serving") is True or entry.get("isServing") is True
        ):
            picked = _pick(entry)
            if picked is not None:
                return picked

    for entry in towers:
        if isinstance(entry, dict):
            picked = _pick(entry)
            if picked is not None:
                return picked

    return None


def _parse_float(value: Any) -> float | None:
    """Parse a signal-strength value (may be a string, empty, or non-numeric) to a float.

    Parameters
    ----------
    value : Any
        Raw value from the API (typically a string like "-90", "", or None).

    Returns
    -------
    float | None
        The parsed float, or None if the value is missing/empty/non-numeric.

    """
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


# ---------------------------------------------------------------------------
# #327 — eSIM inventory (Phase 4B, spec-only)
#
# ⚠ No MG hardware is available to confirm the live response shape; models
# are kept lenient/defensive (see module docstring above for #304's identical
# rationale). MUST be re-verified against a live response in Phase 6.
# ---------------------------------------------------------------------------


class MGEsimServiceProvider(BaseModel):
    """Cellular service-provider info nested in an eSIM profile.

    Not an independently fetched endpoint - nested sub-object of
    ``MGEsimProfile.serviceProvider``. ``plans`` is deliberately not modeled
    field-by-field: plan names are multi-valued per profile and are not
    emitted as metric labels in v1 (unbounded/high-cardinality).
    """

    __meraki_derived__ = True

    name: str | None = None

    model_config = ConfigDict(extra="allow")


class MGEsimProfile(BaseModel):
    """A single eSIM profile entry nested in an eSIM inventory row."""

    __meraki_derived__ = True

    iccid: str | None = None
    status: str | None = None
    serviceProvider: MGEsimServiceProvider | None = None

    model_config = ConfigDict(extra="allow")


class MGEsimDeviceRef(BaseModel):
    """Device reference nested in an eSIM inventory row."""

    __meraki_derived__ = True

    serial: str = ""
    model: str | None = None

    model_config = ConfigDict(extra="allow")


class MGEsimNetworkRef(BaseModel):
    """Network reference nested in an eSIM inventory row."""

    __meraki_derived__ = True

    id: str | None = None

    model_config = ConfigDict(extra="allow")


class MGEsimInventoryRow(BaseModel):
    """Per-eSIM inventory row.

    Source: ``getOrganizationCellularGatewayEsimsInventory`` (#327).
    """

    __meraki_op__ = "getOrganizationCellularGatewayEsimsInventory"

    eid: str = ""
    active: bool | None = None
    device: MGEsimDeviceRef | None = None
    network: MGEsimNetworkRef | None = None
    profiles: list[MGEsimProfile] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")

    def resolved_serial(self) -> str:
        """Resolve the device serial from the nested ``device`` object."""
        if self.device is not None and self.device.serial:
            return self.device.serial
        return ""

    def resolved_network_id(self) -> str | None:
        """Resolve the network ID from the nested ``network`` object."""
        if self.network is not None and self.network.id:
            return self.network.id
        return None

    def active_provider_name(self) -> str:
        """Return the active profile's carrier name, or "" if none/absent.

        "Active" here means the profile whose own ``status`` field is
        ``"active"`` (distinct from the eSIM-level ``active`` boolean).
        Deliberately does NOT surface plan names (multi-valued).
        """
        for profile in self.profiles:
            if profile.status != "active":
                continue
            if profile.serviceProvider is not None and profile.serviceProvider.name:
                return profile.serviceProvider.name
            return ""
        return ""


# ---------------------------------------------------------------------------
# #328 — MG HA role from the device-agnostic org-wide uplinks/statuses
# endpoint (Phase 4B, spec-only)
# ---------------------------------------------------------------------------


class MGHighAvailability(BaseModel):
    """High-availability sub-object nested in an org-wide uplink-status row."""

    __meraki_derived__ = True

    enabled: bool | None = None
    role: str | None = None

    model_config = ConfigDict(extra="allow")


class MGUplinkStatusRow(BaseModel):
    """Per-device row from the device-agnostic org-wide uplinks/statuses endpoint.

    Source: ``getOrganizationUplinksStatuses`` (#328). This endpoint returns
    MX/MG/Z rows; only the ``highAvailability`` object of MG rows is consumed
    here. Per-uplink status/signal is already emitted from the dedicated
    ``getOrganizationCellularGatewayUplinkStatuses`` call
    (``_collect_uplink_status_details``) and is deliberately NOT re-emitted
    from this endpoint; MX rows are left untouched (owned by ``mx.py``).
    """

    __meraki_op__ = "getOrganizationUplinksStatuses"

    networkId: str | None = None
    serial: str = ""
    model: str | None = None
    highAvailability: MGHighAvailability | None = None

    model_config = ConfigDict(extra="allow")


def _is_mg_row(model: str, serial: str, device_lookup: dict[str, dict[str, Any]]) -> bool:
    """Identify whether an org-wide uplinks/statuses row belongs to an MG device.

    The endpoint returns MX/MG/Z rows with no dedicated per-product-type
    filter, so ownership is determined from the row's own ``model`` field
    first, falling back to the device lookup (by serial) when the row omits
    or has an empty ``model`` (#328).

    Parameters
    ----------
    model : str
        The row's own ``model`` field (may be empty).
    serial : str
        The row's device serial.
    device_lookup : dict[str, dict[str, Any]]
        Device lookup table keyed by serial.

    Returns
    -------
    bool
        True if this row should be treated as an MG cellular gateway.

    """
    if model.upper().startswith("MG"):
        return True
    info = device_lookup.get(serial)
    if info is None:
        return False
    looked_up_model = str(info.get("model", ""))
    if looked_up_model.upper().startswith("MG"):
        return True
    return bool(info.get("device_type") == "MG")


class MGCollector(BaseDeviceCollector):
    """Collector for MG cellular gateway metrics."""

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MG collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance.

        """
        super().__init__(parent)

        self._mg_uplink_status_info = self.parent._create_gauge(
            MGMetricName.MG_UPLINK_STATUS_INFO,
            "MG cellular gateway uplink status info (1 = present)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.INTERFACE,
                LabelName.STATUS,
                LabelName.PROVIDER,
                LabelName.CONNECTION_TYPE,
                LabelName.SIGNAL_TYPE,
                LabelName.ROAMING_STATUS,
                LabelName.APN,
                LabelName.IP,
            ],
        )

        signal_labelnames = [
            LabelName.ORG_ID,
            LabelName.NETWORK_ID,
            LabelName.SERIAL,
            LabelName.MODEL,
            LabelName.DEVICE_TYPE,
            LabelName.INTERFACE,
        ]

        self._mg_uplink_signal_rsrp = self.parent._create_gauge(
            MGMetricName.MG_UPLINK_SIGNAL_RSRP_DBM,
            "MG cellular gateway uplink RSRP signal strength in dBm",
            labelnames=signal_labelnames,
        )

        self._mg_uplink_signal_rsrq = self.parent._create_gauge(
            MGMetricName.MG_UPLINK_SIGNAL_RSRQ_DB,
            "MG cellular gateway uplink RSRQ signal quality in dB",
            labelnames=signal_labelnames,
        )

        self._mg_uplink_roaming = self.parent._create_gauge(
            MGMetricName.MG_UPLINK_ROAMING,
            "MG cellular gateway uplink roaming status (1 = roaming, 0 = home)",
            labelnames=signal_labelnames,
        )

        # #304 (Phase 4): cellular band configuration + serving cell.
        self._mg_cellular_bands = self.parent._create_gauge(
            MGMetricName.MG_CELLULAR_BANDS,
            "Count of cellular bands in a given state, per SIM slot and radio access technology",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.SLOT,
                LabelName.CONNECTION_TYPE,
                LabelName.STATUS,
            ],
        )

        self._mg_serving_cell_info = self.parent._create_gauge(
            MGMetricName.MG_SERVING_CELL_INFO,
            "MG cellular gateway current serving cell tower info (1 = present)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.CELL_ID,
                LabelName.TAC,
            ],
        )

        # Phase 4B (#327): eSIM inventory.
        self._mg_esims = self.parent._create_gauge(
            MGMetricName.MG_ESIMS,
            "Number of eSIMs in the organization's cellular gateway eSIM inventory",
            labelnames=[LabelName.ORG_ID],
        )

        self._mg_esim_info = self.parent._create_gauge(
            MGMetricName.MG_ESIM_INFO,
            "Cellular gateway eSIM inventory info (1 = present)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.EID,
                LabelName.SERIAL,
                LabelName.NETWORK_ID,
                LabelName.PROVIDER,
            ],
        )

        self._mg_esim_active = self.parent._create_gauge(
            MGMetricName.MG_ESIM_ACTIVE,
            "Cellular gateway eSIM active status (1 = active)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.EID,
                LabelName.SERIAL,
            ],
        )

        # Phase 4B (#328): HA role from org-wide uplinks/statuses (MG rows only).
        self._mg_ha_enabled = self.parent._create_gauge(
            MGMetricName.MG_HA_ENABLED,
            "Whether high availability is enabled for the cellular gateway (1 = enabled)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
            ],
        )

        self._mg_ha_role = self.parent._create_gauge(
            MGMetricName.MG_HA_ROLE,
            "Cellular gateway high-availability role (1 = current role)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.ROLE,
            ],
        )

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MG-specific metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before this is called.

        Cellular uplink status/signal metrics are collected org-wide via
        collect_uplink_statuses(), not per-device, so this remains a no-op.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        # Uplink statuses are collected separately via collect_uplink_statuses()

    async def collect_uplink_statuses(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect all MG organization-wide metrics for one organization.

        This is the single entry point ``DeviceCollector._collect_mg_specific_metrics``
        invokes, so it fans out to every independently-gated MG org-wide concern:
        uplink status/signal (#617), cellular band configuration + serving
        cell info (#304, Phase 4), eSIM inventory (#327, Phase 4B), and HA
        role (#328, Phase 4B). Each concern is gated by its own scheduler
        group so a stretched interval on one never blocks the others.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        await self._collect_uplink_status_details(org_id, org_name, device_lookup)
        await self._collect_cellular_config(org_id, org_name, device_lookup)
        await self._collect_esim_inventory(org_id, org_name, device_lookup)
        await self._collect_ha_status(org_id, org_name, device_lookup)

    @log_api_call("getOrganizationCellularGatewayUplinkStatuses")
    @with_error_handling(
        operation="Collect MG uplink statuses",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_uplink_status_details(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect cellular uplink statuses for all MG gateways in an organization.

        Update tier: MEDIUM (300s) — cellular uplink status/signal does not change
        second-to-second, and a single org-wide call covers all MG devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        # #617 gate: the mg_uplink_status group is declared on DeviceCollector;
        # skip the org-wide fetch when it is not due this heartbeat.
        if not self.parent._should_run_group(EndpointGroupName.MG_UPLINK_STATUS):
            return

        uplink_statuses = await asyncio.to_thread(
            self.api.cellularGateway.getOrganizationCellularGatewayUplinkStatuses,
            org_id,
            total_pages="all",
        )

        uplink_statuses = validate_response_format(
            uplink_statuses,
            expected_type=list,
            operation="getOrganizationCellularGatewayUplinkStatuses",
        )

        # Successful fetch: advance the group's last-ran clock.
        self.parent._mark_group_ran(EndpointGroupName.MG_UPLINK_STATUS)

        if not uplink_statuses:
            return

        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MG_UPLINK_STATUS)

        # NB: do NOT clear the gauge's label series here. This runs once per org
        # (concurrently across orgs, sharing one gauge instance), so a global
        # _metrics.clear() would wipe every other org's series mid-cycle. Stale
        # label series (status/provider transitions) are removed by the metric
        # expiration manager via parent._set_metric tracking instead.

        # Resolve allowed network IDs for filter enforcement on org-wide responses.
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0
        uplink_count = 0

        for row in uplink_statuses:
            gateway = CellularGatewayUplinkStatus.model_validate(row)
            serial = gateway.serial
            device_info = device_lookup.get(serial, {})
            network_id = (
                gateway.networkId
                if gateway.networkId is not None
                else device_info.get("network_id", "")
            )

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            gateway_model = (
                gateway.model if gateway.model is not None else device_info.get("model", "")
            )
            device_data = {
                "serial": serial,
                "name": device_info.get("name", serial),
                "model": gateway_model,
                "networkId": network_id,
                "networkName": device_info.get("network_name", network_id),
            }

            for uplink in gateway.uplinks:
                uplink_count += 1
                interface = uplink.interface
                status = uplink.status
                roaming = uplink.roaming

                info_labels = create_device_labels(
                    device_data,
                    org_id=org_id,
                    org_name=org_name,
                    interface=interface,
                    status=status,
                    provider=uplink.provider or "",
                    connection_type=uplink.connectionType or "",
                    signal_type=uplink.signalType or "",
                    roaming_status=(roaming.status or "") if roaming is not None else "",
                    apn=uplink.apn or "",
                    ip=uplink.ip or "",
                )
                self.parent._set_metric(
                    self._mg_uplink_status_info,
                    info_labels,
                    1,
                    MGMetricName.MG_UPLINK_STATUS_INFO.value,
                    ttl_seconds=ttl_seconds,
                )

                signal_labels = create_device_labels(
                    device_data,
                    org_id=org_id,
                    org_name=org_name,
                    interface=interface,
                )

                signal = uplink.signalStat
                rsrp = _parse_float(signal.rsrp) if signal is not None else None
                if rsrp is not None:
                    self.parent._set_metric(
                        self._mg_uplink_signal_rsrp,
                        signal_labels,
                        rsrp,
                        MGMetricName.MG_UPLINK_SIGNAL_RSRP_DBM.value,
                        ttl_seconds=ttl_seconds,
                    )

                rsrq = _parse_float(signal.rsrq) if signal is not None else None
                if rsrq is not None:
                    self.parent._set_metric(
                        self._mg_uplink_signal_rsrq,
                        signal_labels,
                        rsrq,
                        MGMetricName.MG_UPLINK_SIGNAL_RSRQ_DB.value,
                        ttl_seconds=ttl_seconds,
                    )

                if "roaming" in uplink.model_fields_set:
                    roaming_value = (
                        1.0 if (roaming is not None and roaming.status == "roaming") else 0.0
                    )
                    self.parent._set_metric(
                        self._mg_uplink_roaming,
                        signal_labels,
                        roaming_value,
                        MGMetricName.MG_UPLINK_ROAMING.value,
                        ttl_seconds=ttl_seconds,
                    )

        logger.debug(
            "Collected MG uplink statuses",
            org_id=org_id,
            gateway_count=len(uplink_statuses),
            uplink_count=uplink_count,
            skipped_count=skipped,
        )

    async def _collect_cellular_config(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect cellular band configuration + serving cell info (#304).

        Two org-wide bulk calls, gated together under a single scheduler group
        (``EndpointGroupName.MG_CELLULAR_CONFIG``, ``cost_fn=2.0`` in
        ``device.py``) since both are low-volatility config-like diagnostics
        for the same feature area.

        ⚠ Spec-only (#304): no MG hardware is available to confirm the live
        response shape against the OpenAPI spec, which is known to be wrong
        for some endpoints (see ``evidence/live-api-verification.md``).
        Parsing is deliberately defensive/lenient - verify field names against
        a live response in Phase 6 before trusting this as final.

        Update tier: MEDIUM (300s heartbeat), scheduler-stretched to a 900s
        floor - band/serving-cell config changes far less often than
        up/down uplink status.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        if not self.parent._should_run_group(EndpointGroupName.MG_CELLULAR_CONFIG):
            return

        await self._fetch_and_emit_cellular_bands(org_id, org_name, device_lookup)
        await self._fetch_and_emit_serving_cells(org_id, org_name, device_lookup)

        # Both underlying calls are attempted whenever this group is due
        # (cost_fn=2.0 in device.py accounts for both together); mark the
        # group ran regardless of either sub-fetch's individual outcome -
        # each already absorbs its own errors via @with_error_handling so a
        # single failed call doesn't block the other or leave the group
        # perpetually "not yet run".
        self.parent._mark_group_ran(EndpointGroupName.MG_CELLULAR_CONFIG)

    @log_api_call("getOrganizationDevicesCellularUplinksBandsByDevice")
    @with_error_handling(
        operation="Collect MG cellular band configuration",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_and_emit_cellular_bands(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Fetch + emit per-(slot, connection_type, status) band counts (#304).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        raw = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevicesCellularUplinksBandsByDevice,
            org_id,
            total_pages="all",
        )

        rows = validate_response_format(
            raw,
            expected_type=list,
            operation="getOrganizationDevicesCellularUplinksBandsByDevice",
        )

        if not rows:
            return

        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MG_CELLULAR_CONFIG)
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )

        skipped = 0
        emitted = 0

        for row in rows:
            band_row = MGCellularBandsDevice.model_validate(row)
            serial = band_row.serial
            device_info = device_lookup.get(serial, {})
            network_id = band_row.resolved_network_id() or device_info.get("network_id", "")

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            model = band_row.model if band_row.model is not None else device_info.get("model", "")
            device_data = {"serial": serial, "model": model, "networkId": network_id}

            for (slot, connection_type, status), count in _count_bands_by_slot(
                band_row.bands
            ).items():
                labels = create_device_labels(
                    device_data,
                    org_id=org_id,
                    org_name=org_name,
                    slot=slot,
                    connection_type=connection_type,
                    status=status,
                )
                self.parent._set_metric(
                    self._mg_cellular_bands,
                    labels,
                    count,
                    MGMetricName.MG_CELLULAR_BANDS.value,
                    ttl_seconds=ttl_seconds,
                )
                emitted += 1

        logger.debug(
            "Collected MG cellular band configuration",
            org_id=org_id,
            device_count=len(rows),
            series_emitted=emitted,
            skipped_count=skipped,
        )

    @log_api_call("getOrganizationDevicesCellularUplinksTowersByDevice")
    @with_error_handling(
        operation="Collect MG serving cell info",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_and_emit_serving_cells(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Fetch + emit the current serving cell tower per MG device (#304).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial.

        """
        raw = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevicesCellularUplinksTowersByDevice,
            org_id,
            total_pages="all",
        )

        rows = validate_response_format(
            raw,
            expected_type=list,
            operation="getOrganizationDevicesCellularUplinksTowersByDevice",
        )

        if not rows:
            return

        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MG_CELLULAR_CONFIG)
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )

        skipped = 0
        emitted = 0

        for row in rows:
            tower_row = MGCellularTowersDevice.model_validate(row)
            serial = tower_row.serial
            device_info = device_lookup.get(serial, {})
            network_id = tower_row.resolved_network_id() or device_info.get("network_id", "")

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            serving_cell = _extract_serving_cell(tower_row.towers)
            if serving_cell is None:
                continue

            cell_id, tac = serving_cell
            model = tower_row.model if tower_row.model is not None else device_info.get("model", "")
            device_data = {"serial": serial, "model": model, "networkId": network_id}

            labels = create_device_labels(
                device_data,
                org_id=org_id,
                org_name=org_name,
                cell_id=cell_id,
                tac=tac,
            )
            self.parent._set_metric(
                self._mg_serving_cell_info,
                labels,
                1,
                MGMetricName.MG_SERVING_CELL_INFO.value,
                ttl_seconds=ttl_seconds,
            )
            emitted += 1

        logger.debug(
            "Collected MG serving cell info",
            org_id=org_id,
            device_count=len(rows),
            series_emitted=emitted,
            skipped_count=skipped,
        )

    @log_api_call("getOrganizationCellularGatewayEsimsInventory")
    @with_error_handling(
        operation="Collect MG eSIM inventory",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_esim_inventory(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect the organization's cellular gateway eSIM inventory (#327).

        ⚠ Spec-only: no MG hardware is available to confirm the live response
        shape against the OpenAPI spec. Plan names
        (``profiles[].serviceProvider.plans[]``) are multi-valued and are
        deliberately NOT emitted as metric labels in v1.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial (fallback source for network
            id resolution when a row omits its nested network reference).

        """
        if not self.parent._should_run_group(EndpointGroupName.MG_ESIMS):
            return

        raw = await asyncio.to_thread(
            self.api.cellularGateway.getOrganizationCellularGatewayEsimsInventory,
            org_id,
        )

        rows = validate_response_format(
            raw,
            expected_type=list,
            operation="getOrganizationCellularGatewayEsimsInventory",
        )

        # Successful fetch: advance the group's last-ran clock.
        self.parent._mark_group_ran(EndpointGroupName.MG_ESIMS)

        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MG_ESIMS)

        # Snapshot count reflects the org-wide inventory total - deliberately
        # NOT filtered by NetworkFilter, matching other org-wide snapshot
        # gauges (e.g. ORG_DEVICES_BY_MODEL).
        self.parent._set_metric(
            self._mg_esims,
            create_labels(org_id=org_id),
            len(rows),
            MGMetricName.MG_ESIMS.value,
            ttl_seconds=ttl_seconds,
        )

        if not rows:
            return

        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )

        skipped = 0
        emitted = 0

        for row in rows:
            esim = MGEsimInventoryRow.model_validate(row)
            serial = esim.resolved_serial()
            device_info = device_lookup.get(serial, {})
            network_id = esim.resolved_network_id() or device_info.get("network_id", "")

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            info_labels = create_labels(
                org_id=org_id,
                eid=esim.eid,
                serial=serial,
                network_id=network_id,
                provider=esim.active_provider_name(),
            )
            self.parent._set_metric(
                self._mg_esim_info,
                info_labels,
                1,
                MGMetricName.MG_ESIM_INFO.value,
                ttl_seconds=ttl_seconds,
            )

            active_labels = create_labels(
                org_id=org_id,
                eid=esim.eid,
                serial=serial,
            )
            self.parent._set_metric(
                self._mg_esim_active,
                active_labels,
                1.0 if esim.active else 0.0,
                MGMetricName.MG_ESIM_ACTIVE.value,
                ttl_seconds=ttl_seconds,
            )
            emitted += 1

        logger.debug(
            "Collected MG eSIM inventory",
            org_id=org_id,
            row_count=len(rows),
            series_emitted=emitted,
            skipped_count=skipped,
        )

    @log_api_call("getOrganizationUplinksStatuses")
    @with_error_handling(
        operation="Collect MG HA status",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_ha_status(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect MG high-availability role from the org-wide uplinks/statuses endpoint (#328).

        This endpoint returns MX/MG/Z rows; ONLY the ``highAvailability``
        object of MG rows is consumed here. Per-uplink status is already
        emitted by ``_collect_uplink_status_details`` (dedicated
        cellularGateway endpoint) and is deliberately NOT re-emitted from
        this call; MX rows are left untouched (``mx.py`` owns MX uplink
        status).

        ⚠ Spec-only: no MG hardware is available to confirm the live
        response shape.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table keyed by serial, used to identify MG rows
            (fallback when a row's own ``model`` is missing/empty) and to
            resolve network id when a row omits it.

        """
        if not self.parent._should_run_group(EndpointGroupName.MG_HA):
            return

        raw = await asyncio.to_thread(
            self.api.organizations.getOrganizationUplinksStatuses,
            org_id,
            total_pages="all",
            perPage=1000,
        )

        rows = validate_response_format(
            raw,
            expected_type=list,
            operation="getOrganizationUplinksStatuses",
        )

        # Successful fetch: advance the group's last-ran clock.
        self.parent._mark_group_ran(EndpointGroupName.MG_HA)

        if not rows:
            return

        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MG_HA)
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )

        skipped = 0
        emitted = 0

        for row in rows:
            status_row = MGUplinkStatusRow.model_validate(row)
            serial = status_row.serial
            model = status_row.model or ""

            if not _is_mg_row(model, serial, device_lookup):
                continue

            device_info = device_lookup.get(serial, {})
            network_id = status_row.networkId or device_info.get("network_id", "")

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            ha = status_row.highAvailability
            if ha is None:
                continue

            if ha.enabled is not None:
                enabled_labels = create_labels(
                    org_id=org_id,
                    network_id=network_id,
                    serial=serial,
                )
                self.parent._set_metric(
                    self._mg_ha_enabled,
                    enabled_labels,
                    1.0 if ha.enabled else 0.0,
                    MGMetricName.MG_HA_ENABLED.value,
                    ttl_seconds=ttl_seconds,
                )

            if ha.role in _KNOWN_HA_ROLES:
                role_labels = create_labels(
                    org_id=org_id,
                    network_id=network_id,
                    serial=serial,
                    role=ha.role,
                )
                self.parent._set_metric(
                    self._mg_ha_role,
                    role_labels,
                    1,
                    MGMetricName.MG_HA_ROLE.value,
                    ttl_seconds=ttl_seconds,
                )

            emitted += 1

        logger.debug(
            "Collected MG HA status",
            org_id=org_id,
            row_count=len(rows),
            series_emitted=emitted,
            skipped_count=skipped,
        )
