"""MR per-AP wireless signal quality (RSSI/SNR) metrics collector (#324)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from ....core.async_utils import ManagedTaskGroup
from ....core.constants import MRMetricName
from ....core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ....core.label_helpers import create_device_labels
from ....core.logging import get_logger
from ....core.logging_decorators import log_api_call
from ....core.logging_helpers import LogContext
from ....core.metrics import LabelName
from ....core.scheduler import EndpointGroupName

if TYPE_CHECKING:
    from ...device import DeviceCollector

logger = get_logger(__name__)


class _SignalQualityRow(BaseModel):
    """One signal-quality-history bucket for an AP.

    The endpoint returns ``snr`` (integer dB) and ``rssi`` (integer dBm) per
    time bucket. Lenient (``extra="allow"``) so additional/renamed fields never
    break parsing.
    """

    model_config = ConfigDict(extra="allow")

    startTs: str | None = None
    endTs: str | None = None
    snr: float | None = None
    rssi: float | None = None


class MRSignalQualityCollector:
    """Collector for per-AP wireless signal quality (RSSI/SNR).

    Per-AP fan-out over ``getNetworkWirelessSignalQualityHistory`` — there is no
    bulk org-wide form. Cost is one API call per *selected* AP per cycle, so the
    fan-out is scoped by the ``ap_signal_quality_tags`` config (client-side tag
    filter using the inventory device rows' ``tags`` — zero extra calls) and can
    be disabled entirely via ``collect_ap_signal_quality``. Bounded by
    ``settings.api.concurrency_limit`` and gated on ``MR_SIGNAL_QUALITY`` (hourly
    floor via the scheduler).
    """

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MR signal quality collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance that owns the metrics.

        """
        self.parent = parent
        self.api = parent.api
        self.settings = parent.settings
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize per-AP signal quality gauges."""
        self._mr_signal_rssi_dbm = self.parent._create_gauge(
            MRMetricName.MR_SIGNAL_RSSI_DBM,
            "Access point received signal strength indicator in dBm "
            "(mean over the trailing 1-hour bucket)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )
        self._mr_signal_snr_db = self.parent._create_gauge(
            MRMetricName.MR_SIGNAL_SNR_DB,
            "Access point signal-to-noise ratio in dB (mean over the trailing 1-hour bucket)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

    def _select_aps(self, devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Select the APs to poll based on config.

        Empty ``ap_signal_quality_tags`` ⇒ every wireless AP; non-empty ⇒ only
        wireless APs whose device ``tags`` intersect the configured set (tags are
        already present on the inventory device rows, so no extra calls).

        Parameters
        ----------
        devices : list[dict[str, Any]]
            All devices in the organization (inventory rows).

        Returns
        -------
        list[dict[str, Any]]
            The subset of wireless APs to poll this cycle.

        """
        aps = [d for d in devices if d.get("productType") == "wireless"]

        tags = list(self.settings.collectors.ap_signal_quality_tags or [])
        if not tags:
            return aps

        selected_tags = set(tags)
        return [d for d in aps if selected_tags.intersection(d.get("tags") or [])]

    @with_error_handling(
        operation="Collect MR signal quality",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_signal_quality(
        self, org_id: str, org_name: str, devices: list[dict[str, Any]]
    ) -> None:
        """Collect per-AP RSSI/SNR for the selected wireless APs.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        devices : list[dict[str, Any]]
            All devices in the organization (inventory rows, carrying ``tags``
            and ``networkId``).

        """
        # Opt-out short-circuit (the scheduler's enabled_fn also zeroes this
        # group when disabled, but respect the flag directly too).
        if not self.settings.collectors.collect_ap_signal_quality:
            return

        # Scheduler gate: skip the whole per-AP fan-out when not due (#617/#623).
        if not self.parent._should_run_group(EndpointGroupName.MR_SIGNAL_QUALITY):
            return

        selected = self._select_aps(devices)
        if not selected:
            logger.debug(
                "MR signal quality: no APs selected for collection",
                org_id=org_id,
            )
            # Nothing to fetch, but mark ran so the gate can stretch normally.
            self.parent._mark_group_ran(EndpointGroupName.MR_SIGNAL_QUALITY)
            return

        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MR_SIGNAL_QUALITY)

        async with ManagedTaskGroup(
            name="mr_signal_quality_aps",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for device in selected:
                serial = device.get("serial", "")
                if not serial or not device.get("networkId"):
                    continue
                await group.create_task(
                    self._collect_ap(org_id, org_name, device, ttl),
                    name=f"signal_quality_{serial}",
                )

        # Mark ran after the per-AP fan-out completes (#617).
        self.parent._mark_group_ran(EndpointGroupName.MR_SIGNAL_QUALITY)

    @log_api_call("getNetworkWirelessSignalQualityHistory")
    @with_error_handling(
        operation="Collect MR signal quality for AP",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_ap(
        self,
        org_id: str,
        org_name: str,
        device: dict[str, Any],
        ttl: float | None,
    ) -> None:
        """Fetch and emit the newest RSSI/SNR bucket for a single AP.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device : dict[str, Any]
            The AP's inventory row (must carry ``serial`` and ``networkId``).
        ttl : float | None
            Fully-resolved per-series TTL for the MR_SIGNAL_QUALITY group.

        """
        serial = device.get("serial", "")
        network_id = device.get("networkId", "")

        with LogContext(org_id=org_id, network_id=network_id):
            raw_history = await asyncio.to_thread(
                self.api.wireless.getNetworkWirelessSignalQualityHistory,
                network_id,
                deviceSerial=serial,
                timespan=7200,
                resolution=3600,
                autoResolution=False,
            )
        history = validate_response_format(
            raw_history,
            expected_type=list,
            operation="getNetworkWirelessSignalQualityHistory",
        )

        rows = [_SignalQualityRow.model_validate(r) for r in history]
        candidates = [r for r in rows if r.snr is not None and r.rssi is not None]
        if not candidates:
            # Empty / all-null history (AP idle or unlicensed feature) — debug-skip.
            logger.debug(
                "MR signal quality: no non-null bucket for AP",
                org_id=org_id,
                serial=serial,
            )
            return

        newest = max(candidates, key=lambda r: r.endTs or "")

        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        self.parent._set_metric(
            self._mr_signal_rssi_dbm,
            device_labels,
            float(newest.rssi),  # type: ignore[arg-type]
            ttl_seconds=ttl,
        )
        self.parent._set_metric(
            self._mr_signal_snr_db,
            device_labels,
            float(newest.snr),  # type: ignore[arg-type]
            ttl_seconds=ttl,
        )
