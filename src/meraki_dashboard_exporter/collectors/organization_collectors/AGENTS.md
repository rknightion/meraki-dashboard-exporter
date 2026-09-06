# Organization collectors

Eight org-scoped sub-collector domains under `OrganizationCollector` (`../organization.py`).
`BaseOrganizationCollector` (`base.py`) adds `self.inventory = getattr(parent, "inventory", None)` on
top of the shared `parent`/`api`/`settings` wiring, so a sub-collector must handle `inventory` being
`None`.

## Not every org metric has a file here

Networks-total, devices-total, devices-by-model, packet captures and application usage are collected
directly inside the coordinator (`_collect_network_metrics`, `_collect_device_metrics`,
`_collect_device_counts_by_model`, `_collect_packet_capture_metrics`,
`_collect_application_usage_metrics`). Point-in-time device availability stays on the coordinator as
`_collect_device_availability_metrics`; only the *change-history* variant moved here as
`device_availability_history.py`. Do not assume an org metric is missing because no module here owns
it.

## Which sub-collectors filter response rows

`firmware.py` and `device_availability_history.py` resolve
`self.inventory.get_allowed_network_ids(org_id)` and skip rows whose network id falls outside it. The
rest return org-scoped aggregates with no per-network breakdown, so the allow-list has nothing to
apply to - `top_usage.py` says so explicitly in its module docstring. Adding a sub-collector whose
response carries network-keyed rows means adding the filter.

## Inventory caching reaches licences too

`LicenseCollector` prefers `self.inventory.get_licenses_overview(org_id)` (30-minute TTL, licence
data rarely changes) and only falls back to a direct `getOrganizationLicensesOverview` call when
`inventory` is unset.

## Licensing model branch (license.py)

`collect()` fetches the overview first. If `overview["licensedDeviceCounts"]` is present the org is
on **co-termination** licensing and `_process_licensing_overview` emits one
`_licenses_total`/`_licenses_expiring` pair per device type, all sharing one expiration date.
Otherwise it is **per-device** licensing: fetch the full `getOrganizationLicenses` list with
`total_pages="all"`, count by `(licenseType, state)`, and flag licences expiring within 30 days
individually. `_parse_meraki_date` handles both ISO and Meraki's human-readable
`"Mar 13, 2027 UTC"` form.

## Stale-zero guard (client_overview.py)

`getOrganizationClientsOverview` sometimes returns client count and every usage field at zero. On
that response `ClientOverviewCollector` logs a warning and re-emits the last cached non-zero values
instead of writing zeros. The replay is bounded: after `_MAX_CONSECUTIVE_ZERO_REPLAYS` (3)
consecutive zero cycles, or once the cache is older than `_MAX_CACHE_AGE_SECONDS` (900), a genuinely
zero org emits real zeros. Metrics that look "stuck" here are the guard working.

`client_overview.py` also wraps its raw dict with `validate_response_format` so an SDK
exhausted-retry error shape raises instead of poisoning that cache with zeros.

## Fixed request parameters

- `getOrganizationClientsOverview` and `getOrganizationApiRequestsOverview`: `timespan=3600`.
- `getOrganizationLicenses`: `total_pages="all"` or the per-device licence list is truncated.
