<system_context>
Device-specific collectors for Meraki Dashboard Exporter - Handles metrics collection for all Meraki device types (MR, MS, MX, MT, MG, MV). Each device type has unique capabilities and metrics.
</system_context>

<critical_notes>
- **Inherit from `BaseDeviceCollector`** (in `base.py`) for consistent device handling
- **Product type filtering**: Use `product_types` parameter when fetching devices
- **Manual registration**: Device collectors are registered in `DeviceCollector` coordinator
- **Metric creation**: Use `self.parent._create_gauge()` (not direct `Gauge()` construction)
</critical_notes>

<file_map>
## DEVICE TYPES & FILES
- `base.py` - `BaseDeviceCollector` ABC with common device patterns; subclasses implement `async collect(device)`
- `mr/` - MR (Wireless APs) - **Nested coordinator pattern**:
  - `mr/collector.py` - `MRCollector` coordinator delegating to sub-collectors
  - `mr/clients.py` - `MRClientsCollector` - Client connection and auth metrics
  - `mr/performance.py` - `MRPerformanceCollector` - Ethernet, packet loss, CPU metrics
  - `mr/wireless.py` - `MRWirelessCollector` - SSID status, radio config, usage metrics
- `ms.py` - MS (Switches) - Port status, PoE, cable diagnostics, STP, packet errors
- `ms_stack.py` - `MSStackCollector` - Switch stack membership and member count metrics
- `mx.py` - MX (Security Appliances) - Coordinator delegating to sub-collectors
- `mx_firewall.py` - `MXFirewallCollector` - L3/L7 firewall rule counts and default policy (SLOW tier)
- `mx_vpn.py` - `MXVpnCollector` - Site-to-site VPN peer status and performance (latency, jitter, loss)
- `mt.py` - MT (Sensors) - Environmental data, water detection, battery
- `mg.py` - MG (Cellular Gateways) - Cellular connectivity, data usage
- `mv.py` - MV (Security Cameras) - Camera health, analytics
</file_map>

<paved_path>
## DEVICE COLLECTOR PATTERN
```python
from ..devices.base import BaseDeviceCollector

class MyDeviceCollector(BaseDeviceCollector):
    def _initialize_metrics(self) -> None:
        self._my_metric = self.parent._create_gauge(
            MyMetricName.SOME_METRIC,
            "Description",
            labelnames=[LabelName.ORG_ID.value, LabelName.SERIAL.value],
        )

    async def collect(self, device: dict[str, Any]) -> None:
        # Called per-device by parent coordinator
        ...
```

## API INTERACTION
```python
# Always use asyncio.to_thread for Meraki SDK calls
channel_data = await asyncio.to_thread(
    self.api.wireless.getOrganizationWirelessDevicesChannelUtilization,
    org_id,
    total_pages="all",
    timespan=3600,
)
```
</paved_path>

<api_quirks>
## MERAKI API DEVICE-SPECIFIC LIMITATIONS
- **MR**: CPU metrics only via `getOrganizationWirelessDevicesSystemCpuLoadHistory`
- **MS**: Some older switches don't support PoE metrics
- **MT**: May return both `temperature` and `rawTemperature` - only use `temperature`
- **MG**: Signal strength varies by carrier and location
- **MV**: Requires camera analytics to be enabled
</api_quirks>

<fatal_implications>
- **NEVER mix device types** in single collector - use product_types filtering
- **NEVER assume all devices support all metrics** - handle missing data gracefully
- **NEVER skip error handling** for device-specific API calls
</fatal_implications>
