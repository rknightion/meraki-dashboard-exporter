<system_context>
Device-specific collectors for Meraki Dashboard Exporter - Handles metrics collection for all Meraki device types (MR, MS, MX, MT, MG, MV). Each device type has unique capabilities and metrics.
</system_context>

<critical_notes>
- **Inherit from BaseDeviceCollector** for consistent device handling patterns
- **Product type filtering**: Use `product_types` parameter when fetching devices
- **Device-specific APIs**: Each device type has unique API endpoints and capabilities
- **Manual registration**: Device collectors are registered in main DeviceCollector coordinator
</critical_notes>

<file_map>
## DEVICE TYPES & FILES
- `base.py` - BaseDeviceCollector with common device patterns
- `mr.py` - MR (Wireless Access Points) - Channel utilization, client stats
- `ms.py` - MS (Switches) - Port status, PoE, cable diagnostics
- `mx.py` - MX (Security Appliances) - VPN, firewall, WAN health
- `mt.py` - MT (Sensors) - Environmental data, water detection
- `mg.py` - MG (Cellular Gateways) - Cellular connectivity, data usage
- `mv.py` - MV (Security Cameras) - Camera health, analytics
</file_map>

<paved_path>
## DEVICE COLLECTOR PATTERN
```python
from .base import BaseDeviceCollector
from ..core.constants.metrics_constants import MetricName
from ..core.metrics import LabelName

class MRCollector(BaseDeviceCollector):
    """Collector for MR (Wireless Access Points) devices"""

    def _initialize_metrics(self) -> None:
        self.channel_utilization = Gauge(
            MetricName.CHANNEL_UTILIZATION.value,
            "Wireless channel utilization percentage",
            [LabelName.ORG_ID.value, LabelName.SERIAL.value, LabelName.BAND.value]
        )

    async def _collect_impl(self) -> None:
        organizations = await self._get_organizations()
        for org in organizations:
            # Only fetch MR devices
            devices = await self._fetch_devices(org.id, product_types=["MR"])
            await self._collect_wireless_metrics(org.id, devices)
```

## API INTERACTION PATTERN
```python
@log_api_call("getOrganizationWirelessDevicesChannelUtilization")
async def _collect_wireless_metrics(self, org_id: str, devices: list[Device]) -> None:
    self._track_api_call("getOrganizationWirelessDevicesChannelUtilization")

    # Call Meraki API
    channel_data = await asyncio.to_thread(
        self.api.wireless.getOrganizationWirelessDevicesChannelUtilization,
        org_id,
        total_pages="all",
        timespan=3600
    )

    # Process and set metrics
    self._update_channel_metrics(org_id, channel_data)
```
</paved_path>

<patterns>
## DEVICE TYPE CAPABILITIES

### MR (Wireless Access Points)
- **Channel utilization**: Per-band channel usage metrics
- **Client connectivity**: Connected client counts and stats
- **RF health**: Radio frequency performance metrics
- **API**: Uses `wireless` controller endpoints

### MS (Switches)
- **Port status**: Individual port up/down status
- **PoE**: Power over Ethernet usage and status
- **Cable diagnostics**: Cable health and performance
- **API**: Uses `switch` controller endpoints

### MX (Security Appliances)
- **VPN status**: Site-to-site VPN tunnel health
- **WAN health**: Uplink performance metrics
- **Firewall**: Connection and threat metrics
- **API**: Uses `appliance` controller endpoints

### MT (Sensors)
- **Environmental**: Temperature, humidity readings
- **Special sensors**: Water detection, door sensors
- **Battery status**: Wireless sensor battery levels
- **API**: Uses sensor-specific endpoints

### MG (Cellular Gateways)
- **Cellular connectivity**: Signal strength, carrier info
- **Data usage**: Cellular data consumption metrics
- **API**: Uses `cellularGateway` endpoints

### MV (Security Cameras)
- **Camera health**: Online status, recording status
- **Analytics**: Motion detection, object recognition
- **API**: Uses `camera` controller endpoints
</patterns>

<examples>
## Complete MR Collector Example
```python
import asyncio
from prometheus_client import Gauge
from ..core.constants.metrics_constants import MetricName
from ..core.metrics import LabelName
from ..core.error_handling import with_error_handling
from ..core.logging_decorators import log_api_call
from .base import BaseDeviceCollector

class MRCollector(BaseDeviceCollector):
    """Collector for MR (Wireless Access Points) devices"""

    def _initialize_metrics(self) -> None:
        self.channel_utilization = Gauge(
            MetricName.CHANNEL_UTILIZATION.value,
            "Wireless channel utilization percentage",
            [LabelName.ORG_ID.value, LabelName.SERIAL.value, LabelName.BAND.value]
        )

        self.client_count = Gauge(
            MetricName.CLIENT_COUNT.value,
            "Connected client count per access point",
            [LabelName.ORG_ID.value, LabelName.SERIAL.value, LabelName.BAND.value]
        )

    @with_error_handling("Collect MR metrics", continue_on_error=True)
    async def _collect_impl(self) -> None:
        organizations = await self._get_organizations()

        for org in organizations:
            devices = await self._fetch_devices(org.id, product_types=["MR"])
            if not devices:
                continue

            await self._collect_channel_utilization(org.id, devices)
            await self._collect_client_counts(org.id, devices)

    @log_api_call("getOrganizationWirelessDevicesChannelUtilization")
    async def _collect_channel_utilization(self, org_id: str, devices: list[Device]) -> None:
        self._track_api_call("getOrganizationWirelessDevicesChannelUtilization")

        try:
            channel_data = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesChannelUtilization,
                org_id,
                total_pages="all",
                timespan=3600
            )

            for reading in channel_data:
                device_serial = reading.get("serial")
                if not device_serial:
                    continue

                # Set metrics for each band
                for band_data in reading.get("byBand", []):
                    band = band_data.get("band")
                    utilization = band_data.get("utilization", {}).get("average", 0)

                    self.channel_utilization.labels(
                        org_id=org_id,
                        serial=device_serial,
                        band=band
                    ).set(utilization)

        except Exception as e:
            self.logger.error(f"Failed to collect channel utilization: {e}")
```

## MS Collector Example (Switches)
```python
class MSCollector(BaseDeviceCollector):
    """Collector for MS (Switches) devices"""

    def _initialize_metrics(self) -> None:
        self.port_status = Gauge(
            MetricName.PORT_STATUS.value,
            "Switch port status (1=up, 0=down)",
            [LabelName.ORG_ID.value, LabelName.SERIAL.value, LabelName.PORT.value]
        )

        self.poe_power = Gauge(
            MetricName.POE_POWER.value,
            "PoE power consumption in watts",
            [LabelName.ORG_ID.value, LabelName.SERIAL.value, LabelName.PORT.value]
        )

    async def _collect_impl(self) -> None:
        organizations = await self._get_organizations()

        for org in organizations:
            devices = await self._fetch_devices(org.id, product_types=["MS"])
            await self._collect_port_status(org.id, devices)
            await self._collect_poe_metrics(org.id, devices)
```
</examples>

<workflow>
## ADDING NEW DEVICE TYPE SUPPORT
1. **Create collector file**: `{device_type}.py` in devices directory
2. **Inherit from BaseDeviceCollector**: Provides common device patterns
3. **Define device-specific metrics**: In `_initialize_metrics()` method
4. **Implement collection logic**: In `_collect_impl()` with proper error handling
5. **Register in coordinator**: Add to DeviceCollector's device_collectors list
6. **Add device constants**: Update device_constants.py if needed
7. **Create tests**: With device factories and metric assertions
</workflow>

<api_quirks>
## MERAKI API DEVICE-SPECIFIC LIMITATIONS
- **MR CPU metrics**: Only available via `getOrganizationWirelessDevicesSystemCpuLoadHistory`
- **MS PoE**: Some older switch models don't support PoE metrics
- **MX uptime**: Not available via API for any device types
- **MT sensor readings**: May return both `temperature` and `rawTemperature` - only use `temperature`
- **MG cellular**: Signal strength varies by carrier and location
- **MV analytics**: Requires camera analytics to be enabled
</api_quirks>

<fatal_implications>
- **NEVER mix device types** in single collector - use product_types filtering
- **NEVER assume all devices support all metrics** - handle missing data gracefully
- **NEVER skip error handling** for device-specific API calls
- **NEVER hardcode device capabilities** - check API documentation for each endpoint
</fatal_implications>
