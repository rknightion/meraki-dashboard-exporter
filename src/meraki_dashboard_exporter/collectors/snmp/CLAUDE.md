# SNMP Collectors

<system_context>
SNMP Collectors - Provides SNMP-based metric collection for Meraki devices and cloud controller. Complements API-based collectors with real-time, granular metrics not available through the Dashboard API.
</system_context>

<critical_notes>
- **DISABLED BY DEFAULT**: Set `MERAKI_EXPORTER_SNMP__ENABLED=true` to enable
- **Dynamic configuration**: SNMP credentials fetched via Dashboard API
- **Two collection modes**: Cloud Controller SNMP and Device SNMP
- **Requires network access**: Cloud SNMP uses public endpoint, Device SNMP needs LAN access
- **pysnmp v7**: Uses async/await patterns exclusively
</critical_notes>

<file_map>
## SNMP COLLECTOR STRUCTURE
- `base.py` - Base SNMP collector with common functionality
- `cloud_controller.py` - Cloud Controller SNMP metrics (organization-level)
- `device_snmp.py` - Device-specific SNMP collectors (MR, MS)
- `snmp_coordinator.py` - Three tier-based coordinators (Fast/Medium/Slow)
</file_map>

<paved_path>
## ENABLING SNMP COLLECTION
```bash
# Enable SNMP collection
export MERAKI_EXPORTER_SNMP__ENABLED=true

# Configure SNMP settings (optional - defaults shown)
export MERAKI_EXPORTER_SNMP__TIMEOUT=5.0
export MERAKI_EXPORTER_SNMP__RETRIES=3
export MERAKI_EXPORTER_SNMP__CONCURRENT_DEVICE_LIMIT=10

# For Organization/Cloud Controller SNMPv3 (required if using v3)
export MERAKI_EXPORTER_SNMP__ORG_V3_AUTH_PASSWORD="your-auth-password"
export MERAKI_EXPORTER_SNMP__ORG_V3_PRIV_PASSWORD="your-priv-password"

# SNMP collection runs at MEDIUM update tier frequency
# Controlled by existing update interval configuration:
export MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM=300  # Default: 300s
```

## ADDING NEW SNMP METRICS
```python
from .base import BaseSNMPCollector

class MyDeviceSNMPCollector(BaseSNMPCollector):
    def _setup_metrics(self) -> None:
        self.my_metric = create_metric(
            Gauge,
            "meraki_snmp_ms_my_metric",  # Must start with meraki_snmp_{type}_
            "Description of metric",
            labelnames=[...]
        )

    async def collect_snmp_metrics(self, target: dict[str, Any]) -> None:
        # Get OID values
        result = await self.snmp_get(target, "1.3.6.1.2.1.1.1.0")

        # Or bulk walk
        results = await self.snmp_bulk(target, "1.3.6.1.2.1.2.2.1")
```
</paved_path>

<patterns>
## SNMP AUTHENTICATION PATTERNS

### Cloud Controller SNMP (Organization)
- Uses organization SNMP settings from `getOrganizationSnmp` API
- Supports SNMPv2c and SNMPv3
- Hostname: `snmp.meraki.com` (or regional variant)
- Port: 16100 (or as configured)
- Requires whitelisted peer IPs
- **v2c**: Uses `v2CommunityString` from API response
- **v3**: Uses `v3User` from API, auth/priv passwords from env vars
  - Auth protocols: SHA (default), MD5
  - Priv protocols: AES128 (default), DES
  - Passwords must be provided via environment variables

### Device SNMP
- Uses network SNMP settings from `getNetworkSnmp` API
- Access modes: 'none', 'community' (v2c), 'users' (v3)
- Direct device IP access required
- Standard port 161
- **v2c**: Uses `communityString` from API response
- **v3**: Uses `username` and `passphrase` from `users` array
  - The passphrase is used as both auth and priv key
  - Default protocols: SHA/AES128

## ERROR HANDLING
```python
# SNMP operations return None on error
result = await self.snmp_get(target, oid)
if result is None:
    # Handle SNMP down scenario
    self.snmp_up_metric.labels(**labels).set(0)
    return

# Process successful results
for oid, value in result:
    # value is already parsed by base class
```

## METRIC NAMING CONVENTION
All SNMP metrics MUST follow this pattern:
- `meraki_snmp_organization_*` - Cloud controller metrics
- `meraki_snmp_mr_*` - MR (wireless) device metrics
- `meraki_snmp_ms_*` - MS (switch) device metrics

For device-specific metrics, include the device type in the metric name:
- `meraki_snmp_mr_bridge_topology_changes_total` - MR-specific metric
- `meraki_snmp_ms_bridge_topology_changes_total` - MS-specific metric
</patterns>

<examples>
## Complete SNMP Collector Example
```python
from prometheus_client import Counter, Gauge
from ...core.metrics import create_metric
from .base import BaseSNMPCollector

class MSInterfaceErrorCollector(BaseSNMPCollector):
    """Collect interface error counters via SNMP."""

    def _setup_metrics(self) -> None:
        self.crc_errors = create_metric(
            Counter,
            "meraki_snmp_ms_interface_crc_errors_total",
            "CRC errors on interface",
            labelnames=[
                LabelName.DEVICE_SERIAL,
                LabelName.INTERFACE_NAME,
            ]
        )

    async def collect_snmp_metrics(self, target: dict[str, Any]) -> None:
        device_info = target["device_info"]

        # Walk interface error table
        crc_oid = "1.3.6.1.4.1.9.2.2.1.1.12"  # locIfInCRC
        results = await self.snmp_bulk(target, crc_oid)

        if results:
            for oid, value in results:
                # Extract interface index from OID
                if_index = oid.split('.')[-1]

                # Set counter value (not increment)
                self.crc_errors.labels(
                    device_serial=device_info["serial"],
                    interface_name=f"port{if_index}"
                )._value.set(value)
```
</examples>

<workflow>
## SNMP COLLECTION FLOW
1. **Three coordinators run independently** → Each at their tier frequency
2. **Each coordinator checks if SNMP enabled** → Skip if disabled
3. **Fetch organization SNMP settings** → Via getOrganizationSnmp API (cached)
4. **Collect metrics based on tier** → Fast/Medium/Slow collectors
5. **Fetch network SNMP settings** → Via getNetworkSnmp API (cached)
6. **Build device targets** → Using device IPs and SNMP creds
7. **Collect device metrics** → With concurrency limits
8. **Handle failures gracefully** → Set up/down metrics

## ADDING NEW OID COLLECTIONS
1. **Identify OIDs** → From MIB or SNMP walk
2. **Choose update tier** → Fast (60s), Medium (300s), or Slow (900s)
3. **Choose collector type** → Cloud vs Device, MR vs MS
4. **Add metric definition** → Following naming convention
5. **Implement collection** → Using base class methods
6. **Register in coordinator** → Add to appropriate tier's `_init_tier_collectors()`
7. **Handle missing values** → SNMP may return None
8. **Test with real devices** → SNMP implementations vary

### Example: Adding a Fast Interface Counter
```python
# In device_snmp.py - create new collector
class MSInterfaceCounterCollector(BaseSNMPCollector):
    """Fast-updating interface counters for MS devices."""
    # ... implementation ...

# In snmp_coordinator.py - register in fast tier
class SNMPFastCoordinator(BaseSNMPCoordinator):
    def _init_tier_collectors(self) -> None:
        self.ms_interface_collector = MSInterfaceCounterCollector(self.settings)
```
</workflow>

<api_quirks>
## SNMP IMPLEMENTATION NOTES
- **TimeTicks conversion**: Base class converts to seconds automatically
- **MAC addresses**: Detected and formatted as colon-separated hex
- **Counter wraparound**: Use Counter type, set _value directly
- **Bulk operations**: Limited by bulk_max_repetitions setting
- **IPv6 support**: Automatically detected from host address
- **Value parsing**: Base class handles type conversion
</api_quirks>

<fatal_implications>
- **NEVER expose SNMP credentials** in logs or metrics
- **NEVER assume SNMP is available** - always check connectivity first
- **NEVER use increment() on Counter metrics** - use _value.set()
- **NEVER block on SNMP timeouts** - use configured timeout values
- **NEVER poll too frequently** - respect device CPU limitations
</fatal_implications>

<hatch>
## ALTERNATIVE APPROACHES

### Custom OID Mapping
```python
# For vendor-specific OIDs not in standard MIBs
CUSTOM_OIDS = {
    "meraki_specific_metric": "1.3.6.1.4.1.29671.1.1.1.1",
}
```

### SNMP Trap Reception
- Not implemented yet
- Would require trap listener on configured port
- Could provide real-time alerts

### MIB Compilation
- Currently using numeric OIDs
- Could compile MIBs for symbolic names
- Trade-off: Complexity vs readability
</hatch>

# Update Frequency Policy

SNMP collectors are organized into three update tiers, each running at different frequencies. Currently, all SNMP collectors are initialized in both FAST and MEDIUM tiers to ensure metrics are collected regardless of which tier is active.

## FAST Tier (60s default)
- **Coordinator**: `SNMPFastCoordinator`
- **Use for**: Real-time metrics that change frequently
- **Current collectors**: CloudControllerSNMP, MRDeviceSNMP, MSDeviceSNMP
- **Examples**: Interface counters, error rates, active client counts
- **Frequency**: `MERAKI_EXPORTER_UPDATE_INTERVALS__FAST`

## MEDIUM Tier (300s default)
- **Coordinator**: `SNMPMediumCoordinator`
- **Use for**: Standard operational metrics
- **Current collectors**: CloudControllerSNMP, MRDeviceSNMP, MSDeviceSNMP (same as FAST)
- **Examples**: Device status, topology changes, uptime
- **Frequency**: `MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM`

## SLOW Tier (900s default)
- **Coordinator**: `SNMPSlowCoordinator`
- **Use for**: Static or rarely changing information
- **Examples**: Hardware inventory, firmware versions (when implemented)
- **Frequency**: `MERAKI_EXPORTER_UPDATE_INTERVALS__SLOW`
- **Current collectors**: None

Device SNMP queries are performed concurrently with configurable limits to prevent overwhelming network devices.

# SNMP OID Testing Tool

When adding new SNMP metrics or troubleshooting OID issues, use the test tool:

```bash
# Test a specific OID
uv run python src/meraki_dashboard_exporter/tools/test_snmp_oids.py get 10.0.100.10 1.3.6.1.2.1.1.1.0

# Walk an OID tree
uv run python src/meraki_dashboard_exporter/tools/test_snmp_oids.py walk 10.0.100.10 1.3.6.1.2.1.17

# Test common OIDs to see what's available
uv run python src/meraki_dashboard_exporter/tools/test_snmp_oids.py common 10.0.100.10

# Search for OIDs by pattern
uv run python src/meraki_dashboard_exporter/tools/test_snmp_oids.py search 10.0.100.10 1.3.6.1 "port"

# Explore available OID trees
uv run python src/meraki_dashboard_exporter/tools/test_snmp_oids.py explore 10.0.100.10
```

## Test Devices
- **MS (Switch)**: 10.0.100.10
- **MR (Wireless)**: 10.0.100.17
- **Community**: knight (v2c)

## Known Limitations
- Meraki devices don't implement all standard MIBs
- No STP OIDs (1.3.6.1.2.1.17.2.*) on MS/MR devices
- Enterprise OIDs (1.3.6.1.4.1.29671) only available via cloud SNMP

## Adding New Metrics Workflow
1. Use the test tool to verify OID exists on target devices
2. Test on both MS and MR to see which support the OID
3. Add metric only for device types that support it
4. Include proper error handling for missing OIDs
