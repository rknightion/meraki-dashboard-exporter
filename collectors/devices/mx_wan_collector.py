"""
MX WAN Uplink Collector
=======================
Collector para métricas de WAN (uplinks) de dispositivos MX.

Agrega las siguientes métricas a Prometheus:
  - meraki_mx_wan_uplink_status       : Estado de cada uplink (0-4)
  - meraki_mx_wan_uplink_sent_bytes   : Bytes enviados por uplink (últimos ~60 s)
  - meraki_mx_wan_uplink_recv_bytes   : Bytes recibidos por uplink (últimos ~60 s)
  - meraki_mx_wan_uplink_latency_ms   : Latencia en ms (loss-and-latency history)
  - meraki_mx_wan_uplink_loss_pct     : Porcentaje de pérdida de paquetes

Endpoints Meraki API utilizados:
  GET /organizations/{orgId}/appliance/uplink/statuses
  GET /organizations/{orgId}/appliance/uplinks/usage/byNetwork
  GET /devices/{serial}/lossAndLatencyHistory

Instrucciones de instalación
-----------------------------
1. Copia este archivo a:
     src/meraki_dashboard_exporter/collectors/devices/mx_wan_collector.py

2. Agrega las constantes de métricas en:
     src/meraki_dashboard_exporter/core/constants/metrics_constants.py
   (ver bloque METRICS_CONSTANTS al final de este archivo)

3. Registra el collector en:
     src/meraki_dashboard_exporter/collectors/devices/__init__.py
   añadiendo:
     from .mx_wan_collector import MXWanCollector   # noqa: F401

4. Reconstruye la imagen Docker:
     docker build -t meraki-dashboard-exporter:local .
     docker run -d \\
       -e MERAKI_EXPORTER_MERAKI__API_KEY=<tu_key> \\
       -p 9099:9099 \\
       meraki-dashboard-exporter:local
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from meraki_dashboard_exporter.collectors.base import BaseDeviceCollector
from meraki_dashboard_exporter.core.constants.metrics_constants import MXWanMetricName
from meraki_dashboard_exporter.core.metrics import LabelName, UpdateTier

if TYPE_CHECKING:
    from meraki_dashboard_exporter.api.client import MerakiAPIClient
    from meraki_dashboard_exporter.core.inventory import OrganizationInventory

logger = logging.getLogger(__name__)

# Mapeo de estado de uplink a valor numérico (igual que el exporter original)
UPLINK_STATUS_MAP: dict[str, int] = {
    "active": 0,
    "ready": 1,
    "connecting": 2,
    "not connected": 3,
    "failed": 4,
}

# Timespan para loss-and-latency history (segundos). 120 s ≈ 2 intervalos de 60 s.
_LATENCY_TIMESPAN = 120


class MXWanCollector(BaseDeviceCollector):
    """
    Collector de métricas WAN para dispositivos MX (Security Appliances).

    Tier: FAST (60 s) — el estado de los uplinks puede cambiar en segundos
    durante un failover.
    """

    UPDATE_TIER = UpdateTier.FAST
    DEVICE_TYPE = "MX"  # filtra solo dispositivos MX

    # ------------------------------------------------------------------
    # Métricas Prometheus
    # ------------------------------------------------------------------

    def _register_metrics(self) -> None:
        """Define las métricas que este collector expone."""

        self._uplink_status = self._create_gauge(
            MXWanMetricName.WAN_UPLINK_STATUS,
            "Estado del uplink WAN del MX "
            "(0=active, 1=ready, 2=connecting, 3=not_connected, 4=failed)",
            labelnames=[
                LabelName.ORGANIZATION_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.NAME,
                LabelName.WAN_INTERFACE,
            ],
        )

        self._uplink_sent_bytes = self._create_gauge(
            MXWanMetricName.WAN_UPLINK_SENT_BYTES,
            "Bytes enviados por el uplink WAN en el último intervalo de colección",
            labelnames=[
                LabelName.ORGANIZATION_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.WAN_INTERFACE,
            ],
        )

        self._uplink_recv_bytes = self._create_gauge(
            MXWanMetricName.WAN_UPLINK_RECV_BYTES,
            "Bytes recibidos por el uplink WAN en el último intervalo de colección",
            labelnames=[
                LabelName.ORGANIZATION_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.WAN_INTERFACE,
            ],
        )

        self._uplink_latency_ms = self._create_gauge(
            MXWanMetricName.WAN_UPLINK_LATENCY_MS,
            "Latencia promedio en ms del uplink WAN (loss-and-latency history)",
            labelnames=[
                LabelName.ORGANIZATION_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.WAN_INTERFACE,
            ],
        )

        self._uplink_loss_pct = self._create_gauge(
            MXWanMetricName.WAN_UPLINK_LOSS_PCT,
            "Porcentaje de pérdida de paquetes del uplink WAN",
            labelnames=[
                LabelName.ORGANIZATION_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.WAN_INTERFACE,
            ],
        )

    # ------------------------------------------------------------------
    # Lógica de colección
    # ------------------------------------------------------------------

    async def _collect(
        self,
        client: MerakiAPIClient,
        inventory: OrganizationInventory,
    ) -> None:
        """
        Punto de entrada principal. Se invoca automáticamente por el scheduler
        cada UPDATE_TIER segundos.
        """
        org_id = inventory.organization_id

        # 1. Estado de uplinks (activo/fallido/etc.)
        await self._collect_uplink_statuses(client, org_id, inventory)

        # 2. Uso de ancho de banda por uplink
        await self._collect_uplink_usage(client, org_id, inventory)

        # 3. Latencia y pérdida de paquetes (por dispositivo MX)
        await self._collect_loss_and_latency(client, org_id, inventory)

    # ------------------------------------------------------------------

    async def _collect_uplink_statuses(
        self,
        client: MerakiAPIClient,
        org_id: str,
        inventory: OrganizationInventory,
    ) -> None:
        """
        GET /organizations/{orgId}/appliance/uplink/statuses
        Devuelve wan1, wan2 (y cellular si aplica) con status, IP, gateway…
        """
        try:
            statuses = await client.appliance.getOrganizationApplianceUplinkStatuses(
                org_id,
                total_pages="all",
            )
        except Exception:
            logger.exception(
                "Error obteniendo uplink statuses para org %s", org_id
            )
            return

        # Construir un lookup serial → device info desde el inventario
        device_map = {d.serial: d for d in inventory.devices if d.model.startswith("MX")}

        for entry in statuses:
            serial = entry.get("serial", "")
            network_id = entry.get("networkId", "")
            device = device_map.get(serial)
            model = device.model if device else entry.get("model", "unknown")
            name = device.name if device else serial

            for uplink in entry.get("uplinks", []):
                interface = uplink.get("interface", "unknown")
                status_str = uplink.get("status", "unknown").lower()
                status_val = UPLINK_STATUS_MAP.get(status_str, 4)

                self._uplink_status.labels(
                    organization_id=org_id,
                    network_id=network_id,
                    serial=serial,
                    model=model,
                    name=name,
                    wan_interface=interface,
                ).set(status_val)

    # ------------------------------------------------------------------

    async def _collect_uplink_usage(
        self,
        client: MerakiAPIClient,
        org_id: str,
        inventory: OrganizationInventory,
    ) -> None:
        """
        GET /organizations/{orgId}/appliance/uplinks/usage/byNetwork
        Bytes enviados/recibidos por cada uplink agrupados por red.
        """
        try:
            usage_list = await client.appliance.getOrganizationApplianceUplinksUsageByNetwork(
                org_id,
                timespan=60,  # último minuto
            )
        except Exception:
            logger.exception(
                "Error obteniendo uplink usage para org %s", org_id
            )
            return

        for network_entry in usage_list:
            network_id = network_entry.get("networkId", "")
            for uplink in network_entry.get("byUplink", []):
                serial = uplink.get("serial", "")
                interface = uplink.get("interface", "unknown")
                sent = uplink.get("sent", 0)
                received = uplink.get("received", 0)

                common_labels = dict(
                    organization_id=org_id,
                    network_id=network_id,
                    serial=serial,
                    wan_interface=interface,
                )
                self._uplink_sent_bytes.labels(**common_labels).set(sent)
                self._uplink_recv_bytes.labels(**common_labels).set(received)

    # ------------------------------------------------------------------

    async def _collect_loss_and_latency(
        self,
        client: MerakiAPIClient,
        org_id: str,
        inventory: OrganizationInventory,
    ) -> None:
        """
        GET /devices/{serial}/lossAndLatencyHistory
        Itera sobre cada dispositivo MX del inventario.

        Nota: este endpoint puede ser costoso en organizaciones con muchos MX.
        Se recomienda filtrar por modelo si es necesario.
        """
        mx_devices = [d for d in inventory.devices if d.model.startswith("MX")]

        for device in mx_devices:
            serial = device.serial
            network_id = getattr(device, "network_id", "")

            # Meraki soporta wan1, wan2 (y cellular en modelos con LTE)
            for interface in ("wan1", "wan2"):
                try:
                    history = await client.devices.getDeviceLossAndLatencyHistory(
                        serial,
                        ip="8.8.8.8",          # IP de destino para el test
                        uplink=interface,
                        timespan=_LATENCY_TIMESPAN,
                        resolution=60,
                    )
                except Exception as exc:
                    # Es normal que wan2 no exista en todos los modelos
                    logger.debug(
                        "No se pudo obtener loss/latency para %s/%s: %s",
                        serial,
                        interface,
                        exc,
                    )
                    continue

                if not history:
                    continue

                # Tomamos el último punto con datos válidos
                latest = next(
                    (
                        point
                        for point in reversed(history)
                        if point.get("latencyMs") is not None
                        and point.get("lossPercent") is not None
                    ),
                    None,
                )
                if latest is None:
                    continue

                common_labels = dict(
                    organization_id=org_id,
                    network_id=network_id,
                    serial=serial,
                    wan_interface=interface,
                )
                self._uplink_latency_ms.labels(**common_labels).set(
                    latest["latencyMs"]
                )
                self._uplink_loss_pct.labels(**common_labels).set(
                    latest["lossPercent"]
                )


# ===========================================================================
# METRICS_CONSTANTS — pega este bloque en:
#   src/meraki_dashboard_exporter/core/constants/metrics_constants.py
# ===========================================================================
#
# class MXWanMetricName(str, Enum):
#     """Nombres de métricas para el collector de WAN del MX."""
#
#     WAN_UPLINK_STATUS      = "meraki_mx_wan_uplink_status"
#     WAN_UPLINK_SENT_BYTES  = "meraki_mx_wan_uplink_sent_bytes"
#     WAN_UPLINK_RECV_BYTES  = "meraki_mx_wan_uplink_recv_bytes"
#     WAN_UPLINK_LATENCY_MS  = "meraki_mx_wan_uplink_latency_ms"
#     WAN_UPLINK_LOSS_PCT    = "meraki_mx_wan_uplink_loss_pct"
#
# ===========================================================================
# LABEL — agrega esto en:
#   src/meraki_dashboard_exporter/core/metrics.py  (class LabelName)
# ===========================================================================
#
#     WAN_INTERFACE = "wan_interface"
#
# ===========================================================================
