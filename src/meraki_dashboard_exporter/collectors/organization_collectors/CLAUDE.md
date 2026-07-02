<system_context>
Organization-level collectors for Meraki Dashboard Exporter - Handles metrics that apply to entire organizations: API usage, license consumption, and client overview statistics.
</system_context>

<critical_notes>
- **This directory holds 5 of the ~9 org-level metric domains.** `api_usage.py`,
  `license.py`, `client_overview.py`, `firmware.py`, and `device_availability_history.py` are
  genuine `BaseOrganizationCollector` sub-collectors. Networks-total, devices-total,
  devices-by-model, packet captures, and application usage are still collected **directly inside
  the parent coordinator** `../organization.py::OrganizationCollector` (its
  `_collect_network_metrics`, `_collect_device_metrics`, `_collect_device_counts_by_model`,
  `_collect_packet_capture_metrics`, `_collect_application_usage_metrics`) — not as modules here.
  Note point-in-time device availability (`_collect_device_availability_metrics`, via
  `getOrganizationDevicesAvailabilities`) stays on the coordinator; only the *change-history*
  variant moved into this directory as `device_availability_history.py`. Don't assume every org
  metric has a sub-collector file in this directory.
- **Inherit from `BaseOrganizationCollector`** (`base.py`) for the shared `parent`/`api`/`settings`
  wiring, plus `self.inventory = getattr(parent, "inventory", None)`.
- **MEDIUM update tier**: `OrganizationCollector` is `@register_collector(UpdateTier.MEDIUM)`
  (300s interval) — it is not SLOW/900s.
- **Manual registration**: the 5 sub-collectors are instantiated in
  `OrganizationCollector.__init__` (`api_usage_collector`, `license_collector`,
  `client_overview_collector`, `firmware_collector`, `device_availability_history_collector`) and
  each exposes `collect(org_id, org_name)`, called from the coordinator's `_collect_api_metrics` /
  `_collect_license_metrics` / `_collect_client_overview` / firmware+availability-history
  equivalents.
- **None of the 5 sub-collectors here fetch networks or devices** — they only call org-scoped
  endpoints (`getOrganizationApiRequestsOverview`, `getOrganizationClientsOverview`,
  `getOrganizationLicensesOverview`/`getOrganizationLicenses`, `getOrganizationFirmwareUpgrades`,
  `getOrganizationDevicesAvailabilitiesChangeHistory`), so the `get_allowed_network_ids`
  allow-list pattern doesn't apply to this directory's code. It's used by the coordinator/device
  collectors instead — see `../../services/CLAUDE.md` for the full inventory contract.
- **License overview is inventory-cached too, not just networks/devices**: `LicenseCollector`
  prefers `self.inventory.get_licenses_overview(org_id)` (30-minute TTL, since license data
  rarely changes), falling back to a direct `getOrganizationLicensesOverview` call only when
  `inventory` is unset.
- **Wrap fetcher responses** with `validate_response_format` from `core.error_handling`
  (`api_usage.py`, `license.py`; `client_overview.py`'s fetch does not wrap its raw dict).
</critical_notes>

<file_map>
## ORGANIZATION COLLECTOR FILES
- `base.py` - `BaseOrganizationCollector(SubCollectorMixin)`: `parent`, `api`, `settings`,
  `inventory` (via `getattr(parent, "inventory", None)`)
- `api_usage.py` - `APIUsageCollector`: API request counts by HTTP status code + total, over the
  last hour, via `getOrganizationApiRequestsOverview`
- `license.py` - `LicenseCollector`: total/expiring license counts; handles both co-termination
  and per-device licensing models (see `api_quirks`)
- `client_overview.py` - `ClientOverviewCollector`: org-wide client count + total/down/upstream
  usage (KB) over the last hour, via `getOrganizationClientsOverview`
- `firmware.py` - `FirmwareCollector`: firmware upgrade event counts (incl. a pending-total gauge
  for `scheduled`/`pending`/`started` statuses), via `getOrganizationFirmwareUpgrades`
  (`total_pages="all"`)
- `device_availability_history.py` - `DeviceAvailabilityHistoryCollector`: windowed device
  availability *change* counts (not point-in-time status — that's the coordinator's
  `_collect_device_availability_metrics`), via `getOrganizationDevicesAvailabilitiesChangeHistory`
  with a 300s timespan matching the MEDIUM collection cadence
</file_map>

<paved_path>
## ORGANIZATION COLLECTOR PATTERN
```python
from .base import BaseOrganizationCollector


class MyOrgCollector(BaseOrganizationCollector):
    @log_api_call("getOrganizationSomeEndpoint")
    async def _fetch_something(self, org_id: str) -> dict[str, Any]:
        self._track_api_call("getOrganizationSomeEndpoint")
        response = await asyncio.to_thread(self.api.organizations.getOrganizationSomeEndpoint, org_id)
        return validate_response_format(response, expected_type=dict, operation="getOrganizationSomeEndpoint")

    async def collect(self, org_id: str, org_name: str) -> None:
        data = await self._fetch_something(org_id)
        labels = create_org_labels({"id": org_id, "name": org_name})
        self._set_metric_value("_my_gauge_attr", labels, value)  # gauge lives on the parent
```
As with `network_health_collectors/`, gauges are created once in
`OrganizationCollector._initialize_metrics()` (`../organization.py`) and sub-collectors set them
by attribute-name string via `SubCollectorMixin._set_metric_value`.

## LICENSING MODEL BRANCH (`license.py`)
`collect()` fetches the licenses overview first; if `overview["licensedDeviceCounts"]` is present
the org uses **co-termination licensing** (`_process_licensing_overview` sets one
`_licenses_total`/`_licenses_expiring` pair per device type, all sharing one expiration date).
Otherwise it's **per-device licensing**: fetch the full `getOrganizationLicenses` list
(`total_pages="all"`) and `_process_per_device_licenses` counts by `(licenseType, state)` and
flags licenses expiring within 30 days individually via `_parse_meraki_date` (handles both ISO
and Meraki's `"Mar 13, 2027 UTC"` human-readable format).

## STALE-ZERO GUARD (`client_overview.py`)
`ClientOverviewCollector` keeps a per-instance `_last_non_zero_values: dict[str, dict]` cache. If
`getOrganizationClientsOverview` comes back with client count and all usage fields at zero
(a known API glitch), it logs a warning and re-emits the last cached non-zero values for that org
instead of writing zeros. Non-zero responses update the cache. Keep this in mind if metrics look
"stuck" — that's the guard working as intended, not a stale collector.
</paved_path>

<api_quirks>
- **Client overview and API usage timespans are both fixed at exactly 3600s** (1 hour) —
  `getOrganizationClientsOverview` and `getOrganizationApiRequestsOverview` are both called with
  `timespan=3600`.
- **License pagination**: `getOrganizationLicenses` requires `total_pages="all"` to get the full
  per-device license list.
- **404 handling is inconsistent across the 5 collectors**: `client_overview.py`, `license.py`,
  `firmware.py`, and `device_availability_history.py` all special-case `"404" in str(e)` as "not
  available for this org" (`debug` log, no exception raised/logged, re-raising only non-404
  errors for the decorator to handle); `api_usage.py` is the outlier with no such branch — it
  always logs via `logger.exception` on any failure. Match the existing per-file convention
  rather than "fixing" this asymmetry as a drive-by change.
- **Rate limiting**: organization-level calls count toward per-org rate limits like any other API
  call.
</api_quirks>

<fatal_implications>
- **NEVER aggregate across organizations** without proper labeling
- **NEVER skip timespan validation** for endpoints with specific requirements
- **NEVER call `getOrganizationNetworks`/`getOrganizationDevices` directly** - go through
  `self.inventory` (or the parent coordinator's `api_helper`, which itself routes through
  inventory) so `NetworkFilter` applies
</fatal_implications>
