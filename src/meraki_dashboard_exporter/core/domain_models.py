"""Domain models for internal data structures and API responses.

This module extends api_models.py with additional domain models for
specific device types and metric collections.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator

# Network Health Models


class RFHealthData(BaseModel):
    """RF health data for wireless networks."""

    # apidrift: transformed RF-health shape, not a direct API response object.
    __meraki_derived__ = True

    serial: str
    apName: str | None = None
    model: str
    band2_4GhzUtilization: float | None = Field(None, alias="2.4GhzUtilization")
    band5GhzUtilization: float | None = Field(None, alias="5GhzUtilization")
    timestamp: datetime | None = None

    @field_validator("band2_4GhzUtilization", "band5GhzUtilization", mode="before")
    @classmethod
    def validate_utilization(cls, v: Any) -> float | None:
        """Ensure utilization is a float between 0 and 100."""
        if v is None:
            return None
        val = float(v)
        return max(0.0, min(100.0, val))

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ConnectionStats(BaseModel):
    """Wireless connection statistics."""

    __meraki_op__ = "getNetworkWirelessConnectionStats"

    assoc: int = 0
    auth: int = 0
    dhcp: int = 0
    dns: int = 0
    success: int = 0

    @field_validator("*", mode="before")
    @classmethod
    def validate_counts(cls, v: Any) -> int:
        """Ensure counts are non-negative integers."""
        if v is None:
            return 0
        return max(0, int(v))


class NetworkConnectionStats(BaseModel):
    """Network-wide connection statistics response."""

    # apidrift: wrapper composing ConnectionStats, not a single API response.
    __meraki_derived__ = True

    networkId: str
    connectionStats: ConnectionStats

    model_config = ConfigDict(extra="allow")


class DataRate(BaseModel):
    """Wireless data rate information."""

    # apidrift: computed rate model (download/upload kbps), not a raw response.
    __meraki_derived__ = True

    total: int = 0
    sent: int = 0
    received: int = 0

    @field_validator("*", mode="before")
    @classmethod
    def validate_bytes(cls, v: Any) -> int:
        """Ensure byte counts are non-negative integers."""
        if v is None:
            return 0
        return max(0, int(v))

    @computed_field
    def download_kbps(self) -> float:
        """Calculate download rate in kbps."""
        # Assuming this is bytes over last 5 minutes (300 seconds)
        return (self.received * 8) / 1000 / 300 if self.received > 0 else 0.0

    @computed_field
    def upload_kbps(self) -> float:
        """Calculate upload rate in kbps."""
        # Assuming this is bytes over last 5 minutes (300 seconds)
        return (self.sent * 8) / 1000 / 300 if self.sent > 0 else 0.0


# Device-specific Models


class SwitchPort(BaseModel):
    """Enhanced switch port model with POE and traffic data."""

    # apidrift: enhanced/derived port-config shape (sourced from a switch-port
    # config endpoint not in the consumed read path), not a single live response.
    __meraki_derived__ = True

    portId: str
    name: str | None = None
    enabled: bool = True
    poeEnabled: bool = False
    type: str = "trunk"
    vlan: int | None = None
    voiceVlan: int | None = None
    allowedVlans: str = "all"
    isolationEnabled: bool = False
    rstpEnabled: bool = True
    stpGuard: Literal["disabled", "root guard", "bpdu guard", "loop guard"] = "disabled"
    linkNegotiation: str = "Auto negotiate"
    accessPolicyType: Literal[
        "Open", "Custom access policy", "MAC allow list", "Sticky MAC allow list"
    ] = "Open"
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class SwitchPortPOE(BaseModel):
    """Switch port POE status and configuration."""

    # apidrift: computed POE model (utilization_percent), not a raw response.
    __meraki_derived__ = True

    portId: str
    isAllocated: bool = False
    allocatedInWatts: float = 0.0
    drawInWatts: float = 0.0

    @field_validator("allocatedInWatts", "drawInWatts", mode="before")
    @classmethod
    def validate_watts(cls, v: Any) -> float:
        """Ensure wattage is non-negative float."""
        if v is None:
            return 0.0
        return max(0.0, float(v))

    @computed_field
    def utilization_percent(self) -> float:
        """Calculate POE utilization percentage."""
        if self.allocatedInWatts <= 0:
            return 0.0
        return min(100.0, (self.drawInWatts / self.allocatedInWatts) * 100)


class STPConfiguration(BaseModel):
    """Spanning Tree Protocol configuration for switches."""

    __meraki_op__ = "getNetworkSwitchStp"

    rstpEnabled: bool = True
    stpBridgePriority: list[dict[str, Any]] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def switch_priorities(self) -> dict[str, int]:
        """Mapping of switch serial to STP priority."""
        result = {}
        for priority_group in self.stpBridgePriority:
            priority = priority_group.get("stpPriority", 32768)  # Default STP priority
            switches = priority_group.get("switches", [])
            for switch_serial in switches:
                result[switch_serial] = priority
        return result

    model_config = ConfigDict(extra="allow")


class MRDeviceStats(BaseModel):
    """MR (Access Point) specific statistics."""

    # apidrift: aggregated/computed AP stats from several wireless endpoints.
    __meraki_derived__ = True

    serial: str
    clientCount: int = 0
    meshNeighbors: int = 0
    repeaterClients: int = 0
    cpuUsagePercent: float | None = None
    memoryUsagePercent: float | None = None

    # Packet loss metrics
    backgroundTrafficLossPercent: float | None = None
    bestEffortTrafficLossPercent: float | None = None
    videoTrafficLossPercent: float | None = None
    voiceTrafficLossPercent: float | None = None

    @field_validator("cpuUsagePercent", "memoryUsagePercent", mode="before")
    @classmethod
    def validate_percentage(cls, v: Any) -> float | None:
        """Ensure percentage is between 0 and 100."""
        if v is None:
            return None
        val = float(v)
        return max(0.0, min(100.0, val))

    @field_validator("clientCount", "meshNeighbors", "repeaterClients", mode="before")
    @classmethod
    def validate_counts(cls, v: Any) -> int:
        """Ensure counts are non-negative integers."""
        if v is None:
            return 0
        return max(0, int(v))

    model_config = ConfigDict(extra="allow")


class MRRadioStatus(BaseModel):
    """MR radio status information."""

    # apidrift: transformed radio-status shape, not a single raw response.
    __meraki_derived__ = True

    serial: str
    radioIndex: int
    operatingChannel: int | None = None
    transmitPower: float | None = None
    standard: str | None = None
    enabled: bool = True

    @field_validator("radioIndex", mode="before")
    @classmethod
    def validate_radio_index(cls, v: Any) -> int:
        """Ensure radio index is valid."""
        val = int(v)
        if val not in {0, 1, 2}:  # 0=2.4GHz, 1=5GHz, 2=6GHz
            raise ValueError(f"Invalid radio index: {val}")
        return val

    model_config = ConfigDict(extra="allow")


# Configuration and Management Models


class ConfigurationChange(BaseModel):
    """Configuration change event."""

    __meraki_op__ = "getOrganizationConfigurationChanges"

    ts: datetime
    adminId: str | None = None
    adminName: str | None = None
    adminEmail: str | None = None
    networkId: str | None = None
    networkName: str | None = None
    page: str | None = None
    label: str | None = None
    oldValue: Any = None
    newValue: Any = None

    model_config = ConfigDict(extra="allow")


# Sensor Models


class SensorMeasurement(BaseModel):
    """Individual sensor measurement."""

    # apidrift: computed measurement shape (normalized_unit), not a raw response.
    __meraki_derived__ = True

    metric: Literal[
        "temperature",
        "humidity",
        "water",
        "door",
        "tvoc",
        "co2",
        "noise",
        "pm25",
        "no2",
        "o3",
        "pm10",
        "indoorAirQuality",
        "battery",
        "voltage",
        "current",
        "realPower",
        "apparentPower",
        "powerFactor",
        "frequency",
        "downstreamPower",
        "remoteLockout",
        "remoteLockoutSwitch",
    ]
    value: float
    unit: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, v: Any) -> float:
        """Ensure value is a float."""
        if v is None:
            raise ValueError("Sensor value cannot be None")
        return float(v)

    @computed_field
    def normalized_unit(self) -> str:
        """Get normalized unit based on metric type."""
        unit_map = {
            "temperature": "celsius",
            "humidity": "percent",
            "water": "boolean",
            "door": "boolean",
            "tvoc": "ppb",
            "co2": "ppm",
            "noise": "dB",
            "pm25": "ug/m3",
            "no2": "ppb",
            "o3": "ppb",
            "pm10": "ug/m3",
            "indoorAirQuality": "score",
            "battery": "percent",
            "voltage": "volts",
            "current": "amperes",
            "realPower": "watts",
            "apparentPower": "volt-amperes",
            "powerFactor": "percent",
            "frequency": "hertz",
            "downstreamPower": "boolean",
            "remoteLockout": "boolean",
            "remoteLockoutSwitch": "boolean",
        }
        return unit_map.get(self.metric, self.unit or "unknown")


class MTSensorReading(BaseModel):
    """MT sensor reading with all measurements."""

    # apidrift: transformed MT reading composing SensorMeasurement list.
    __meraki_derived__ = True

    serial: str
    networkId: str
    timestamp: datetime
    measurements: list[SensorMeasurement]

    model_config = ConfigDict(extra="allow")


# Appliance Security Models


class ApplianceSecurityEvent(BaseModel):
    """A single MX appliance security event (IDS/IPS or AMP).

    The Meraki security-events endpoint returns loosely-typed rows
    (the OpenAPI schema is ``additionalProperties: true``), so this model pins
    only the fields we aggregate on and permits extras.
    """

    __meraki_op__ = "getOrganizationApplianceSecurityEvents"

    ts: datetime | None = None
    eventType: str | None = None
    networkId: str | None = None

    model_config = ConfigDict(extra="allow")


# Appliance HA / Uplink / VPN / Firewall Models (M3 new-signal fetchers, F-023)


class ApplianceRedundancyDesignation(BaseModel):
    """A single warm-spare designation (device + priority) within a network."""

    # apidrift: nested sub-object of ApplianceDeviceRedundancy.designations; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    serial: str = ""
    priority: int | None = None

    model_config = ConfigDict(extra="allow")


class ApplianceDeviceRedundancy(BaseModel):
    """Per-network MX warm-spare (HA) redundancy row.

    Source: ``getOrganizationApplianceDevicesRedundancyByNetwork``.
    """

    __meraki_op__ = "getOrganizationApplianceDevicesRedundancyByNetwork"

    networkId: str = ""
    name: str | None = None
    enabled: bool | None = None
    mode: str = ""
    designations: list[ApplianceRedundancyDesignation] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ApplianceUplinkUsageEntry(BaseModel):
    """A single (device, uplink) usage entry within an uplink-usage row."""

    # apidrift: nested sub-object of ApplianceUplinkUsage.byUplink; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    serial: str = ""
    interface: str = ""
    sent: float | None = None
    received: float | None = None

    model_config = ConfigDict(extra="allow")


class ApplianceUplinkUsage(BaseModel):
    """Per-network MX uplink usage row.

    Source: ``getOrganizationApplianceUplinksUsageByNetwork``.
    """

    __meraki_op__ = "getOrganizationApplianceUplinksUsageByNetwork"

    networkId: str = ""
    name: str | None = None
    byUplink: list[ApplianceUplinkUsageEntry] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ApplianceVpnUsageSummary(BaseModel):
    """VPN usage volume summary for a peer network."""

    # apidrift: nested sub-object of ApplianceVpnStatsPeer.usageSummary; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    sentInKilobytes: float | None = None
    receivedInKilobytes: float | None = None

    model_config = ConfigDict(extra="allow")


class ApplianceVpnLatencySummary(BaseModel):
    """VPN latency summary for one sender/receiver uplink combination."""

    # apidrift: nested sub-object of ApplianceVpnStatsPeer.latencySummaries; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    avgLatencyMs: float | None = None

    model_config = ConfigDict(extra="allow")


class ApplianceVpnStatsPeer(BaseModel):
    """A single peer-network entry within a VPN stats row."""

    # apidrift: nested sub-object of ApplianceVpnStats.merakiVpnPeers; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    networkId: str = ""
    usageSummary: ApplianceVpnUsageSummary | None = None
    latencySummaries: list[ApplianceVpnLatencySummary] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ApplianceVpnStats(BaseModel):
    """Per-network historical VPN usage/latency stats row.

    Source: ``getOrganizationApplianceVpnStats``.
    """

    __meraki_op__ = "getOrganizationApplianceVpnStats"

    networkId: str = ""
    networkName: str | None = None
    merakiVpnPeers: list[ApplianceVpnStatsPeer] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ApplianceFirewallRule(BaseModel):
    """A single L3 or L7 firewall rule.

    Only ``comment``/``policy`` (used for default-rule exclusion and default
    policy detection) are pinned; the differing L7 rule fields are permitted
    via extras.
    """

    # apidrift: nested sub-object of ApplianceFirewallRules.rules; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    comment: str | None = None
    policy: str | None = None

    model_config = ConfigDict(extra="allow")


class ApplianceFirewallRules(BaseModel):
    """A firewall rules response (L3 or L7).

    Source: ``getNetworkApplianceFirewallL3FirewallRules`` /
    ``getNetworkApplianceFirewallL7FirewallRules``.
    """

    __meraki_op__ = [
        "getNetworkApplianceFirewallL3FirewallRules",
        "getNetworkApplianceFirewallL7FirewallRules",
    ]

    rules: list[ApplianceFirewallRule] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# Phase 4 MX config-drift models (#285-#289, v1-readiness). ⚠ spec-only (no MX
# hardware available) — all fields optional/lenient pending Phase-6 live verification.


class ApplianceContentFiltering(BaseModel):
    """Content-filtering configuration for a network.

    Source: ``getNetworkApplianceContentFiltering``.
    """

    __meraki_op__ = "getNetworkApplianceContentFiltering"

    blockedUrlCategories: list[dict[str, Any]] = Field(default_factory=list)
    blockedUrlPatterns: list[str] = Field(default_factory=list)
    allowedUrlPatterns: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ApplianceSecurityMalwareSettings(BaseModel):
    """Advanced Malware Protection (AMP) configuration for a network.

    Source: ``getNetworkApplianceSecurityMalware``. Returns 400/404 when the
    network's org lacks an Advanced Security license -- callers must treat that
    as a debug-log skip, not an error.
    """

    __meraki_op__ = "getNetworkApplianceSecurityMalware"

    mode: str | None = None
    allowedUrls: list[dict[str, Any]] = Field(default_factory=list)
    allowedFiles: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ApplianceSecurityIntrusionSettings(BaseModel):
    """IDS/IPS (intrusion detection/prevention) configuration for a network.

    Source: ``getNetworkApplianceSecurityIntrusion``. Returns 400/404 when the
    network's org lacks an Advanced Security license -- callers must treat that
    as a debug-log skip, not an error.
    """

    __meraki_op__ = "getNetworkApplianceSecurityIntrusion"

    mode: str | None = None
    idsRulesets: str | None = None

    model_config = ConfigDict(extra="allow")


class ApplianceDhcpSubnet(BaseModel):
    """A single DHCP-served subnet's IP utilization row for an MX device.

    Source: ``getDeviceApplianceDhcpSubnets`` (returns a bare list; empty when
    the device serves no DHCP VLANs).
    """

    __meraki_op__ = "getDeviceApplianceDhcpSubnets"

    subnet: str | None = None
    vlanId: int | None = None
    usedCount: int | None = None
    freeCount: int | None = None

    model_config = ConfigDict(extra="allow")


class ApplianceVpnSiteToSiteHub(BaseModel):
    """A single configured VPN hub within a site-to-site VPN config."""

    # apidrift: nested sub-object of ApplianceVpnSiteToSite.hubs; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    hubId: str | None = None

    model_config = ConfigDict(extra="allow")


class ApplianceVpnSiteToSiteSubnet(BaseModel):
    """A single locally-advertised subnet within a site-to-site VPN config."""

    # apidrift: nested sub-object of ApplianceVpnSiteToSite.subnets; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    localSubnet: str | None = None
    useVpn: bool | None = None

    model_config = ConfigDict(extra="allow")


class ApplianceVpnSiteToSite(BaseModel):
    """Site-to-site VPN topology configuration for a network.

    Source: ``getNetworkApplianceVpnSiteToSiteVpn``. ``mode: "none"`` is a
    normal, expected response (VPN not configured for this network).
    """

    __meraki_op__ = "getNetworkApplianceVpnSiteToSiteVpn"

    mode: str = "none"
    hubs: list[ApplianceVpnSiteToSiteHub] = Field(default_factory=list)
    subnets: list[ApplianceVpnSiteToSiteSubnet] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class AppliancePortForwardingRules(BaseModel):
    """Port-forwarding rules configured for a network.

    Source: ``getNetworkApplianceFirewallPortForwardingRules``. An empty
    ``rules`` list is a normal, expected response.
    """

    __meraki_op__ = "getNetworkApplianceFirewallPortForwardingRules"

    rules: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ApplianceOneToOneNatRules(BaseModel):
    """1:1 NAT rules configured for a network.

    Source: ``getNetworkApplianceFirewallOneToOneNatRules``. An empty
    ``rules`` list is a normal, expected response.
    """

    __meraki_op__ = "getNetworkApplianceFirewallOneToOneNatRules"

    rules: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ApplianceOneToManyNatRules(BaseModel):
    """1:many NAT rules configured for a network.

    Source: ``getNetworkApplianceFirewallOneToManyNatRules``. An empty
    ``rules`` list is a normal, expected response.
    """

    __meraki_op__ = "getNetworkApplianceFirewallOneToManyNatRules"

    rules: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ApplianceVlan(BaseModel):
    """A single configured VLAN row for a network.

    Source: ``getNetworkApplianceVlans`` (returns a bare list; the endpoint
    itself returns HTTP 400 when VLANs are not enabled for the network --
    callers must treat that as a debug-log skip, not an error).
    """

    __meraki_op__ = "getNetworkApplianceVlans"

    id: str | int | None = None

    model_config = ConfigDict(extra="allow")


class ApplianceStaticRoute(BaseModel):
    """A single configured static route row for a network.

    Source: ``getNetworkApplianceStaticRoutes`` (returns a bare list).
    """

    __meraki_op__ = "getNetworkApplianceStaticRoutes"

    enabled: bool | None = None

    model_config = ConfigDict(extra="allow")


# Sensor overview / gateway-connection Models (M3 new-signal fetchers, F-023)


class SensorAlertsOverviewByMetric(BaseModel):
    """Currently-alerting sensor overview for a network, keyed by metric.

    Source: ``getNetworkSensorAlertsCurrentOverviewByMetric``. ``counts`` values
    may be ints or nested dicts (e.g. ``noise: {ambient: N}``), so the mapping is
    kept loosely typed and normalized by the collector.
    """

    __meraki_op__ = "getNetworkSensorAlertsCurrentOverviewByMetric"

    supportedMetrics: list[str] = Field(default_factory=list)
    counts: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class SensorGatewayNodeRef(BaseModel):
    """A sensor or gateway reference (serial + optional name)."""

    # apidrift: nested sub-object of SensorGatewayConnection; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    serial: str = ""
    name: str | None = None

    model_config = ConfigDict(extra="allow")


class SensorGatewayNetworkRef(BaseModel):
    """A network reference within a sensor-gateway connection item."""

    # apidrift: nested sub-object of SensorGatewayConnection.network; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    id: str = ""
    name: str | None = None

    model_config = ConfigDict(extra="allow")


class SensorGatewayConnection(BaseModel):
    """Latest sensor-to-gateway connectivity item.

    Source: ``getOrganizationSensorGatewaysConnectionsLatest``.
    """

    __meraki_op__ = "getOrganizationSensorGatewaysConnectionsLatest"

    sensor: SensorGatewayNodeRef = Field(default_factory=SensorGatewayNodeRef)
    gateway: SensorGatewayNodeRef = Field(default_factory=SensorGatewayNodeRef)
    network: SensorGatewayNetworkRef = Field(default_factory=SensorGatewayNetworkRef)
    rssi: int | None = None
    lastConnectedAt: str | None = None

    model_config = ConfigDict(extra="allow")


# Cellular Gateway (MG) Models (F-029)


class CellularGatewayUplinkSignalStat(BaseModel):
    """Signal strength readings for a single MG cellular uplink.

    ``rsrp``/``rsrq`` are typically numeric strings (e.g. ``"-90"``) but may be
    empty or non-numeric; the collector does its own float parsing/tolerance,
    so these are kept loosely typed here.
    """

    # apidrift: nested sub-object of CellularGatewayUplink.signalStat; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    rsrp: Any = None
    rsrq: Any = None

    model_config = ConfigDict(extra="allow")


class CellularGatewayUplinkRoaming(BaseModel):
    """Roaming status object for a single MG cellular uplink."""

    # apidrift: nested sub-object of CellularGatewayUplink.roaming; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    status: str | None = None

    model_config = ConfigDict(extra="allow")


class CellularGatewayUplink(BaseModel):
    """A single uplink entry within a cellular gateway uplink-status row."""

    # apidrift: nested sub-object of CellularGatewayUplinkStatus.uplinks; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    interface: str = ""
    status: str = "not connected"
    provider: str | None = None
    connectionType: str | None = None
    signalType: str | None = None
    roaming: CellularGatewayUplinkRoaming | None = None
    apn: str | None = None
    ip: str | None = None
    signalStat: CellularGatewayUplinkSignalStat | None = None

    model_config = ConfigDict(extra="allow")


class CellularGatewayUplinkStatus(BaseModel):
    """Per-device MG cellular gateway uplink status row.

    Source: ``getOrganizationCellularGatewayUplinkStatuses``.
    """

    __meraki_op__ = "getOrganizationCellularGatewayUplinkStatuses"

    serial: str = ""
    model: str | None = None
    networkId: str | None = None
    uplinks: list[CellularGatewayUplink] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# Switch (MS) Power Module Models (F-029)


class PowerModuleNetworkRef(BaseModel):
    """A network reference nested within a power-module-status row."""

    # apidrift: nested sub-object of DevicePowerModuleStatus.network; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    id: str | None = None

    model_config = ConfigDict(extra="allow")


class PowerModuleSlot(BaseModel):
    """A single power-supply slot entry within a power-module-status row."""

    # apidrift: nested sub-object of DevicePowerModuleStatus.slots; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    number: int | str | None = None
    serial: str | None = None
    model: str | None = None
    status: str | None = None

    model_config = ConfigDict(extra="allow")


class DevicePowerModuleStatus(BaseModel):
    """Per-device MS/rackmount power-module status row.

    Source: ``getOrganizationDevicesPowerModulesStatusesByDevice``.
    """

    __meraki_op__ = "getOrganizationDevicesPowerModulesStatusesByDevice"

    serial: str | None = None
    name: str | None = None
    model: str | None = None
    network: PowerModuleNetworkRef | None = None
    slots: list[PowerModuleSlot] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# Appliance (MX) Uplink Loss/Latency Models (F-029)


class UplinkLossLatencyTimeSeriesPoint(BaseModel):
    """A single timestamped loss/latency sample within an uplink health row."""

    # apidrift: nested sub-object of DeviceUplinkLossLatency.timeSeries; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    ts: str | None = None
    lossPercent: float | None = None
    latencyMs: float | None = None

    model_config = ConfigDict(extra="allow")


class DeviceUplinkLossLatency(BaseModel):
    """Per-(device, uplink, destination-ip) WAN loss/latency row.

    Source: ``getOrganizationDevicesUplinksLossAndLatency``.
    """

    __meraki_op__ = "getOrganizationDevicesUplinksLossAndLatency"

    networkId: str | None = None
    serial: str | None = None
    uplink: str | None = None
    ip: str | None = None
    timeSeries: list[UplinkLossLatencyTimeSeriesPoint] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# Camera (MV) Models (F-029)


class CameraAnalyticsZone(BaseModel):
    """A single configured analytics zone on an MV camera.

    Source: ``getDeviceCameraAnalyticsZones``.

    LIVE-VERIFIED 2026-07-03 (MV12W, org 669910444571368738; #630): the zone key
    on the wire is ``zoneId`` (e.g. ``{"zoneId": "0", "label": "Full Frame"}``),
    NOT ``id`` as the earlier spec-derived assumption held (F-024) — the vendored
    OpenAPI schema for this endpoint is empty, so that "verified against spec"
    note was hollow. The mismatch silently broke the ``meraki_mv_zone_info`` →
    ``meraki_mv_people_count`` join (people-count is keyed on the ``zoneId`` from
    ``getDeviceCameraAnalyticsRecent``, but ``id`` never populated so every zone
    resolved to ``"None"``). ``zoneId`` is now primary; ``id`` is still accepted
    as a fallback for forward/backward compatibility.
    """

    __meraki_op__ = "getDeviceCameraAnalyticsZones"

    zoneId: str | int | None = Field(default=None, validation_alias=AliasChoices("zoneId", "id"))
    label: str | None = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CameraAnalyticsLiveZoneData(BaseModel):
    """Live per-zone analytics counts within a live-analytics response."""

    # apidrift: nested sub-object of CameraAnalyticsLive.zones; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    person: int = 0

    @field_validator("person", mode="before")
    @classmethod
    def validate_person(cls, v: Any) -> int:
        """Ensure person count is a non-negative integer."""
        if v is None:
            return 0
        return max(0, int(v))

    model_config = ConfigDict(extra="allow")


class CameraAnalyticsLive(BaseModel):
    """Live analytics response for an MV camera.

    Source: ``getDeviceCameraAnalyticsLive``.
    """

    __meraki_op__ = "getDeviceCameraAnalyticsLive"

    zones: dict[str, CameraAnalyticsLiveZoneData] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class CameraQualityAndRetention(BaseModel):
    """Quality/retention configuration for an MV camera.

    Source: ``getDeviceCameraQualityAndRetention``.
    """

    __meraki_op__ = "getDeviceCameraQualityAndRetention"

    motionBasedRetentionEnabled: bool | None = None
    audioRecordingEnabled: bool | None = None
    restrictedBandwidthModeEnabled: bool | None = None
    quality: str | None = None
    resolution: str | None = None
    profileId: str | int | None = None

    model_config = ConfigDict(extra="allow")


# Organization Models


class OrganizationSummary(BaseModel):
    """Organization summary with device and network counts."""

    # apidrift: computed cross-endpoint aggregate, not a single API response.
    __meraki_derived__ = True

    id: str
    name: str
    deviceCounts: dict[str, int] = Field(default_factory=dict)
    networkCount: int = 0
    wirelessNetworkCount: int = 0
    switchNetworkCount: int = 0
    applianceNetworkCount: int = 0
    cameraNetworkCount: int = 0
    sensorNetworkCount: int = 0

    @computed_field
    def total_devices(self) -> int:
        """Calculate total device count."""
        return sum(self.deviceCounts.values())

    @field_validator("deviceCounts", mode="before")
    @classmethod
    def validate_device_counts(cls, v: Any) -> dict[str, int]:
        """Ensure device counts are valid."""
        if not isinstance(v, dict):
            return {}
        return {k: max(0, int(val)) for k, val in v.items() if val is not None}


# Client Models


class ClientData(BaseModel):
    """Enhanced client data with resolved hostname."""

    # apidrift: enriched getNetworkClients shape; DNS/derived fields surface as
    # INFO model-extra (expected), real upstream drift still caught by oasdiff.
    __meraki_op__ = "getNetworkClients"

    id: str
    mac: str
    description: str | None = None
    hostname: str | None = None  # Resolved via reverse DNS
    calculatedHostname: str | None = None  # The actual hostname used in metrics
    ip: str | None = None
    ip6: str | None = None
    ip6Local: str | None = None
    user: str | None = None
    firstSeen: datetime
    lastSeen: datetime
    manufacturer: str | None = None
    os: str | None = None
    deviceTypePrediction: str | None = None
    recentDeviceSerial: str | None = None
    recentDeviceName: str | None = None
    recentDeviceMac: str | None = None
    recentDeviceConnection: Literal["Wired", "Wireless"] | str | None = None
    ssid: str | None = None
    vlan: str | None = None
    switchport: str | None = None
    status: Literal["Online", "Offline"] | str = "Offline"
    usage: dict[str, float] | None = None
    notes: str | None = None
    groupPolicy8021x: str | None = None
    adaptivePolicyGroup: str | None = None
    smInstalled: bool = False
    namedVlan: str | None = None
    pskGroup: str | None = None
    wirelessCapabilities: str | None = None
    networkId: str | None = None
    networkName: str | None = None
    organizationId: str | None = None

    @computed_field
    def effective_ssid(self) -> str:
        """Get effective SSID (use 'Wired' for wired connections)."""
        if self.recentDeviceConnection == "Wired":
            return "Wired"
        return self.ssid or "Unknown"

    @computed_field
    def display_name(self) -> str:
        """Get best available display name."""
        return self.description or self.hostname or self.mac

    model_config = ConfigDict(extra="allow")


# Wireless (MR) SSID Firewall Models (Phase 4, #290)


class WirelessSsid(BaseModel):
    """A single SSID configuration row for a network.

    Source: ``getNetworkWirelessSsids``.
    """

    __meraki_op__ = "getNetworkWirelessSsids"

    number: int | None = None
    name: str | None = None
    enabled: bool | None = None

    model_config = ConfigDict(extra="allow")


class WirelessSsidFirewallRule(BaseModel):
    """A single L3 or L7 firewall rule for an SSID.

    Only ``comment``/``policy`` (used for default-rule exclusion) are pinned;
    the differing L7 rule fields are permitted via extras.
    """

    # apidrift: nested sub-object of WirelessSsidFirewallL3Rules/L7Rules.rules;
    # not an independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    comment: str | None = None
    policy: str | None = None

    model_config = ConfigDict(extra="allow")


class WirelessSsidFirewallL3Rules(BaseModel):
    """The L3 firewall rules response for an SSID (includes ``allowLanAccess``).

    Source: ``getNetworkWirelessSsidFirewallL3FirewallRules``.
    """

    __meraki_op__ = "getNetworkWirelessSsidFirewallL3FirewallRules"

    rules: list[WirelessSsidFirewallRule] = Field(default_factory=list)
    allowLanAccess: bool | None = None

    model_config = ConfigDict(extra="allow")


class WirelessSsidFirewallL7Rules(BaseModel):
    """The L7 firewall rules response for an SSID.

    Source: ``getNetworkWirelessSsidFirewallL7FirewallRules``.
    """

    __meraki_op__ = "getNetworkWirelessSsidFirewallL7FirewallRules"

    rules: list[WirelessSsidFirewallRule] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# Wireless (MR) RF Profile Assignment Models (Phase 4, #291)


class WirelessRfProfileNetworkRef(BaseModel):
    """A network reference nested within an RF-profile-assignment row."""

    # apidrift: nested sub-object of WirelessRfProfileAssignment.network; not an
    # independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    id: str | None = None
    name: str | None = None

    model_config = ConfigDict(extra="allow")


class WirelessRfProfileRef(BaseModel):
    """The RF profile reference nested within an RF-profile-assignment row."""

    # apidrift: nested sub-object of WirelessRfProfileAssignment.rfProfile; not
    # an independently-mapped response (parent-op drift is caught by oasdiff).
    __meraki_derived__ = True

    id: str | int | None = None
    name: str | None = None
    isIndoorDefault: bool | None = None
    isOutdoorDefault: bool | None = None

    model_config = ConfigDict(extra="allow")


class WirelessRfProfileAssignment(BaseModel):
    """Per-device RF profile assignment row.

    Source: ``getOrganizationWirelessRfProfilesAssignmentsByDevice``.
    """

    __meraki_op__ = "getOrganizationWirelessRfProfilesAssignmentsByDevice"

    serial: str | None = None
    name: str | None = None
    network: WirelessRfProfileNetworkRef | None = None
    rfProfile: WirelessRfProfileRef | None = None

    model_config = ConfigDict(extra="allow")


# Helper function to convert raw API responses to domain models


def parse_rf_health_response(data: dict[str, Any]) -> RFHealthData | None:
    """Parse RF health API response to domain model.

    Parameters
    ----------
    data : dict[str, Any]
        Raw API response data.

    Returns
    -------
    RFHealthData | None
        Parsed RF health data or None if parsing fails.

    """
    try:
        return RFHealthData(**data)
    except Exception:
        return None


def parse_connection_stats(data: dict[str, Any]) -> ConnectionStats:
    """Parse connection stats from API response.

    Parameters
    ----------
    data : dict[str, Any]
        Raw connection stats data.

    Returns
    -------
    ConnectionStats
        Parsed connection statistics with defaults for missing values.

    """
    return ConnectionStats(**data)
