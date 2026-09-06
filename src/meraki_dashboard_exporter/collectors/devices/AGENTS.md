# Device collectors

## Two sub-collector shapes

- Per-device-type collectors extend `BaseDeviceCollector` (`base.py`) and expose
  `async collect(device)`, which `DeviceCollector` calls once per device.
- Metric-domain sub-collectors that a device-type collector composes internally (`mx_firewall.py`,
  `mx_vpn.py`, `ms_stack.py`, and the `mr/` submodules) do not extend `BaseDeviceCollector`. They
  take a `parent` in `__init__`, mostly mix in `SubCollectorMixin`, and expose their own
  `collect`/`collect_for_network`/`collect_*` methods called directly by the owning coordinator.
  There is no uniform interface across them, so do not assume one when wiring a new call site.

`mr/` is the only device type split into its own subpackage.

## Gauges

Create through `self.parent._create_gauge()`, never a direct `Gauge()`. Set through
`self.parent._set_metric()` so expiration tracking works. This differs from
`network_health_collectors/` and `organization_collectors/`, where the gauge is created on the
coordinator and set by attribute-name string.

`_set_metric` buckets a series under the calling collector's own class name, and because device
sub-collectors delegate to the parent, every device series is tracked as `DeviceCollector`.

## Ownership is not what the filename suggests

`DeviceCollector.__init__` instantiates the MX org-wide sub-collectors directly
(`mx_ha_collector`, `mx_uplink_usage_collector`, `mx_uplink_health_collector`) alongside
`ms_stack_collector` and `ms_power_collector`. They are not owned by `mx.py` or `ms.py` despite the
filenames, so a change to the MX coordinator does not reach them.

## Never clear a shared gauge's label series

An org-wide sub-collector method runs once per org, concurrently across orgs, against one shared
gauge instance. Clearing the gauge's series there wipes every other org's series mid-cycle. Stale
label series after a status transition are removed by the metric expiration manager via
`parent._set_metric` tracking instead.

## Device family quirks

- **MS**: the org-level `getOrganizationSwitchPortsStatusesBySwitch` endpoint is absent on older SDK
  versions. `MSCollector` probes for it once (`_org_port_status_supported`, cached) and falls back to
  per-device `getDeviceSwitchPortsStatuses`. PoE budget is not exposed by the API at all; the gauge
  exists but stays unpopulated and would need a per-model lookup table.
- **MS stacks**: PSU, fan and temperature hardware health is deliberately deferred pending Meraki
  API investigation, not missing by accident.
- **MX**: `mx_vpn.py` merges Meraki and third-party peers out of one org-level response. A
  third-party peer carries no `networkId` and is keyed by its public IP instead, so a path that
  assumes `networkId` is present drops or mislabels them.
- **MT**: `MTCollector` has two constructors, `as_subcollector` (under `DeviceCollector`) and
  `as_standalone` (used by `../mt_sensor.py`), so a change to `mt.py` lands in two collectors.
  Responses can carry both `temperature` and `rawTemperature`. Only `temperature` is used;
  `rawTemperature` is undocumented and deliberately skipped.
- **MG**: per-device `collect()` is a no-op by design. The real cellular metrics come from the
  org-wide `collect_uplink_statuses()`, so do not add a per-device cellular fetch on the assumption
  one is missing.
- **MG and MV**: response contracts for surfaces the available hardware cannot exercise are modelled
  deliberately lenient and marked unverified in the source. Verify against the live API before
  tightening one.
