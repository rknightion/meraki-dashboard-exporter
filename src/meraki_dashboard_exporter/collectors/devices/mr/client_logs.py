"""MR per-client wireless DATA-LOG producers (#323 packet loss, #622 signal quality).

These producers emit structured OTLP **data-log records** through the shared
``DataLogEmitter`` (``core/otel_data_logs.py``) — they create **zero Prometheus
series**. Per-client wireless detail (packet loss, signal quality) is an unbounded,
churny population and must never become a labelled metric (see the project cardinality
rules in ``CLAUDE.md`` and the boundary rule in ``otel_data_logs.py``). Operators with
an OTLP log backend (Loki, Elastic, ...) get per-client visibility at zero metric cost;
everyone else pays nothing because the emitter is off by default.

Two events are produced, both gated on the emitter's per-event allowlist so a
disabled event costs **no API calls** at all:

- ``WIRELESS_CLIENT_PACKET_LOSS`` (#323, PRIMARY): one org-wide bulk call
  (``getOrganizationWirelessDevicesPacketLossByClient``) → one record per client row.
  Clean, cheap, always the primary producer.
- ``WIRELESS_CLIENT_SIGNAL_QUALITY`` (#622, EXPERIMENTAL / off by default): there is
  **no bulk per-client signal source** in the SDK, only the per-client
  ``getNetworkWirelessSignalQualityHistory(clientId=...)`` fan-out — i.e. **one API
  call per active client per cycle**. This is potentially very expensive on large
  orgs, so it is off by default, ``ManagedTaskGroup``-bounded, and its client universe
  is derived from the same packet-loss bulk response (active clients only) rather than
  a separate client enumeration. Treat as experimental until proven.

Wiring: ``collect_client_logs`` is folded into ``MRCollector.collect_ssid_usage``
(an existing org-level MR pass that already receives ``org_id``/``org_name``), so no
new top-level ``DeviceCollector`` call site / no ``device.py`` edit is needed.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict

from ....core.async_utils import ManagedTaskGroup
from ....core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ....core.logging import get_logger
from ....core.logging_decorators import log_api_call
from ....core.logging_helpers import LogContext
from ....core.otel_data_logs import DataLogEvent

if TYPE_CHECKING:
    from ....core.otel_data_logs import DataLogEmitter
    from ...device import DeviceCollector

logger = get_logger(__name__)

#: Window for the per-client packet-loss bulk fetch (matches the byNetwork/byDevice
#: packet-loss metric family's 5-minute window in ``performance.py``).
PACKET_LOSS_WINDOW_SECONDS = 300

#: Signal-quality history fetch window / bucket resolution (mirrors the per-AP
#: signal-quality collector, ``signal_quality.py``: newest non-null 1-hour bucket).
SIGNAL_QUALITY_TIMESPAN_SECONDS = 7200
SIGNAL_QUALITY_RESOLUTION_SECONDS = 3600


class _LossDirection(BaseModel):
    """One direction (downstream/upstream) of a per-client packet-loss row.

    Lenient (``extra="allow"``) so renamed/added fields never break parsing.
    """

    model_config = ConfigDict(extra="allow")

    total: int | None = None
    lost: int | None = None
    lossPercentage: float | None = None


class _ClientRef(BaseModel):
    """Client identity block on a per-client packet-loss row."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    mac: str | None = None


class _NetworkRef(BaseModel):
    """Network identity block on a per-client packet-loss row."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    name: str | None = None


class _PacketLossByClientRow(BaseModel):
    """One row of ``getOrganizationWirelessDevicesPacketLossByClient``.

    Verified against the OpenAPI spec: each row carries ``downstream`` /
    ``upstream`` (``total``/``lost``/``lossPercentage``), ``client`` (``id``/
    ``mac``) and ``network`` (``id``/``name``). The response does **not** carry
    the associated AP serial, so ``device.serial`` is deliberately not emitted.
    """

    model_config = ConfigDict(extra="allow")

    downstream: _LossDirection | None = None
    upstream: _LossDirection | None = None
    client: _ClientRef | None = None
    network: _NetworkRef | None = None


class _SignalQualityRow(BaseModel):
    """One signal-quality-history bucket (``snr`` dB / ``rssi`` dBm)."""

    model_config = ConfigDict(extra="allow")

    startTs: str | None = None
    endTs: str | None = None
    snr: float | None = None
    rssi: float | None = None


class MRClientLogsCollector:
    """Emits per-client wireless data-log records (packet loss + signal quality).

    Creates NO Prometheus metrics. All output goes through
    ``self.parent.data_log_emitter`` (may be ``None`` — then this is a no-op). Both
    events are gated on ``is_event_enabled`` so a disabled event skips the API call
    entirely (zero rate-limit cost for non-users).
    """

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize the MR client-logs producer.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance (owns ``data_log_emitter``, ``api``,
            ``settings`` and ``inventory``).

        """
        self.parent = parent
        self.api = parent.api
        self.settings = parent.settings

    @with_error_handling(
        operation="Collect MR per-client data logs",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_client_logs(self, org_id: str, org_name: str) -> None:
        """Fetch + emit per-client packet-loss (and optionally signal-quality) logs.

        Skips ALL work (including the API fetch) unless the emitter exists and at
        least one of the two events is enabled — non-users pay zero cost.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        emitter = self.parent.data_log_emitter
        if emitter is None:
            return

        want_packet_loss = emitter.is_event_enabled(DataLogEvent.WIRELESS_CLIENT_PACKET_LOSS)
        want_signal_quality = emitter.is_event_enabled(DataLogEvent.WIRELESS_CLIENT_SIGNAL_QUALITY)
        if not want_packet_loss and not want_signal_quality:
            # Both events disabled → do NOT touch the API (zero rate-limit cost).
            return

        rows = await self._fetch_packet_loss_by_client(org_id)
        if not rows:
            logger.debug("No per-client packet-loss data available", org_id=org_id)
            return

        # Enforce NetworkFilter on the org-wide response (rows carry network.id).
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )

        parsed: list[_PacketLossByClientRow] = []
        skipped = 0
        for raw in rows:
            row = _PacketLossByClientRow.model_validate(raw)
            network_id = row.network.id if row.network else None
            if not network_id:
                continue
            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue
            parsed.append(row)

        if skipped:
            logger.debug(
                "MR client logs: skipped rows outside network filter",
                org_id=org_id,
                skipped_count=skipped,
            )

        if want_packet_loss:
            self._emit_packet_loss(emitter, org_id, org_name, parsed)

        if want_signal_quality:
            await self._collect_signal_quality(emitter, org_id, org_name, parsed)

    @log_api_call("getOrganizationWirelessDevicesPacketLossByClient")
    async def _fetch_packet_loss_by_client(self, org_id: str) -> list[dict[str, Any]] | None:
        """Fetch the org-wide per-client packet-loss rows (one bulk call).

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]] | None
            The per-client rows, or ``None`` on an empty/error-shaped response.

        """
        with LogContext(org_id=org_id):
            raw = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesPacketLossByClient,
                org_id,
                total_pages="all",
                timespan=PACKET_LOSS_WINDOW_SECONDS,
            )
        rows = validate_response_format(
            raw,
            expected_type=list,
            operation="getOrganizationWirelessDevicesPacketLossByClient",
        )
        return cast("list[dict[str, Any]]", rows)

    def _emit_packet_loss(
        self,
        emitter: DataLogEmitter,
        org_id: str,
        org_name: str,
        rows: list[_PacketLossByClientRow],
    ) -> None:
        """Emit one WIRELESS_CLIENT_PACKET_LOSS record per client row.

        Parameters
        ----------
        emitter : DataLogEmitter
            The (enabled) data-log emitter.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        rows : list[_PacketLossByClientRow]
            Network-filtered per-client packet-loss rows.

        """
        for row in rows:
            client = row.client or _ClientRef()
            network = row.network or _NetworkRef()
            client_id = client.id or client.mac or ""
            if not client_id:
                continue

            down = row.downstream or _LossDirection()
            up = row.upstream or _LossDirection()

            attributes: dict[str, str | int | float | bool] = {
                "org.id": org_id,
                "org.name": org_name,
                "network.id": network.id or "",
                "network.name": network.name or network.id or "",
                "client.id": client_id,
                "data.window_seconds": PACKET_LOSS_WINDOW_SECONDS,
            }
            self._add_numeric(attributes, "downstream.total_packets", down.total)
            self._add_numeric(attributes, "downstream.lost_packets", down.lost)
            self._add_numeric(attributes, "downstream.loss_percent", down.lossPercentage)
            self._add_numeric(attributes, "upstream.total_packets", up.total)
            self._add_numeric(attributes, "upstream.lost_packets", up.lost)
            self._add_numeric(attributes, "upstream.loss_percent", up.lossPercentage)

            total_loss_percent = self._total_loss_percent(down, up)
            self._add_numeric(attributes, "total.loss_percent", total_loss_percent)

            # PII: only build the MAC when identifiers are opted in (the emitter
            # also strips it defensively regardless — see PII_ATTRIBUTE_KEYS).
            if emitter.include_identifiers and client.mac:
                attributes["client.mac"] = client.mac

            emitter.emit(
                DataLogEvent.WIRELESS_CLIENT_PACKET_LOSS,
                attributes,
                body=(
                    f"client {client_id} packet loss "
                    f"down={self._fmt_pct(down.lossPercentage)} "
                    f"up={self._fmt_pct(up.lossPercentage)}"
                ),
            )

    async def _collect_signal_quality(
        self,
        emitter: DataLogEmitter,
        org_id: str,
        org_name: str,
        rows: list[_PacketLossByClientRow],
    ) -> None:
        """Fan out per-client signal-quality fetches and emit one record per client.

        EXPERIMENTAL / off by default: one ``getNetworkWirelessSignalQualityHistory``
        call **per client**. The client universe is the active clients from the
        packet-loss bulk response (deduplicated on network.id + client.id), bounded
        by ``settings.api.concurrency_limit``.

        Parameters
        ----------
        emitter : DataLogEmitter
            The (enabled) data-log emitter.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        rows : list[_PacketLossByClientRow]
            Network-filtered per-client rows (source of the client universe).

        """
        # Deduplicate on (network_id, client_id) — a client can appear once here,
        # but be defensive against duplicate rows.
        seen: set[tuple[str, str]] = set()
        targets: list[tuple[str, str, str | None]] = []
        for row in rows:
            client = row.client or _ClientRef()
            network = row.network or _NetworkRef()
            client_id = client.id
            network_id = network.id
            if not client_id or not network_id:
                continue
            key = (network_id, client_id)
            if key in seen:
                continue
            seen.add(key)
            targets.append((network_id, client_id, client.mac))

        if not targets:
            return

        logger.debug(
            "MR client signal-quality: per-client fan-out (experimental)",
            org_id=org_id,
            client_count=len(targets),
        )

        async with ManagedTaskGroup(
            name="mr_client_signal_quality",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for network_id, client_id, client_mac in targets:
                await group.create_task(
                    self._emit_signal_quality_for_client(
                        emitter, org_id, org_name, network_id, client_id, client_mac
                    ),
                    name=f"client_signal_quality_{client_id}",
                )

    @log_api_call("getNetworkWirelessSignalQualityHistory")
    @with_error_handling(
        operation="Collect MR client signal quality",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _emit_signal_quality_for_client(
        self,
        emitter: DataLogEmitter,
        org_id: str,
        org_name: str,
        network_id: str,
        client_id: str,
        client_mac: str | None,
    ) -> None:
        """Fetch the newest RSSI/SNR bucket for one client and emit a record.

        Parameters
        ----------
        emitter : DataLogEmitter
            The (enabled) data-log emitter.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        network_id : str
            The client's network ID.
        client_id : str
            The client ID (used as the ``clientId`` filter).
        client_mac : str | None
            The client MAC (PII; only emitted when identifiers are opted in).

        """
        with LogContext(org_id=org_id, network_id=network_id):
            raw_history = await asyncio.to_thread(
                self.api.wireless.getNetworkWirelessSignalQualityHistory,
                network_id,
                clientId=client_id,
                timespan=SIGNAL_QUALITY_TIMESPAN_SECONDS,
                resolution=SIGNAL_QUALITY_RESOLUTION_SECONDS,
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
            logger.debug(
                "MR client signal-quality: no non-null bucket",
                org_id=org_id,
                client_id=client_id,
            )
            return

        newest = max(candidates, key=lambda r: r.endTs or "")

        attributes: dict[str, str | int | float | bool] = {
            "org.id": org_id,
            "org.name": org_name,
            "network.id": network_id,
            "client.id": client_id,
            "signal.rssi_dbm": float(newest.rssi),  # type: ignore[arg-type]
            "signal.snr_db": float(newest.snr),  # type: ignore[arg-type]
            "data.window_seconds": SIGNAL_QUALITY_RESOLUTION_SECONDS,
        }
        if emitter.include_identifiers and client_mac:
            attributes["client.mac"] = client_mac

        emitter.emit(
            DataLogEvent.WIRELESS_CLIENT_SIGNAL_QUALITY,
            attributes,
            body=(f"client {client_id} signal rssi={newest.rssi}dBm snr={newest.snr}dB"),
        )

    @staticmethod
    def _add_numeric(
        attributes: dict[str, str | int | float | bool],
        key: str,
        value: int | float | None,
    ) -> None:
        """Add a numeric attribute only when present (skips ``None``)."""
        if value is not None:
            attributes[key] = value

    @staticmethod
    def _total_loss_percent(down: _LossDirection, up: _LossDirection) -> float | None:
        """Combined bidirectional loss percentage, or ``None`` when uncomputable."""
        if down.total is None or up.total is None:
            return None
        total_packets = down.total + up.total
        if total_packets <= 0:
            return None
        total_lost = (down.lost or 0) + (up.lost or 0)
        return (total_lost / total_packets) * 100

    @staticmethod
    def _fmt_pct(value: float | None) -> str:
        """Format a loss percentage for the record body."""
        return "n/a" if value is None else f"{value:.2f}%"
