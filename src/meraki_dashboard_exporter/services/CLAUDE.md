<system_context>
Supporting services for the Meraki Dashboard Exporter - shared inventory caching, client data storage, DNS resolution, and the `/status` health-dashboard aggregator. `inventory.py` is the single enforcement point for the project-wide `NetworkFilter` rule (see root `CLAUDE.md` fatal_implications) — every collector's network/device reads must go through it.
</system_context>

<critical_notes>
- **`OrganizationInventory` (`inventory.py`) is the mandatory network/device read path.** It is constructed once in `collectors/manager.py::CollectorManager.__init__` with a live `NetworkFilter(settings.network_filter)` and shared by all collectors as `self.inventory` / `parent.inventory`. Never call `getOrganizationNetworks`/`getOrganizationDevices`/`getOrganizationDevicesAvailabilities` directly from a collector.
- **The internal cache always stores the full, unfiltered API response.** `NetworkFilter` is applied on every *read* (`get_networks`, `get_devices`, `get_device_availabilities`), not on write, so `invalidate()`/`force_refresh` semantics stay simple and one org-wide fetch serves both filtered and unfiltered callers.
- **`unfiltered=True` is an audit-only escape hatch.** It exists on `get_networks`, `get_devices`, and `get_device_availabilities` for exactly two legitimate uses: (1) internal recursive calls that need the full network set to resolve `allowed_ids` (see `get_devices`/`_maybe_filter_availabilities` falling back to `get_networks(org_id, unfiltered=True)` on a cache miss), and (2) `core/discovery.py::DiscoveryService`, the one sanctioned collector-level bypass. Do not add new `unfiltered=True` call sites in collectors.
- **`services/__init__.py` re-exports `ClientStore`, `DNSResolver`, `OrganizationInventory` only** — `StatusService` is imported directly from `services.status` (not re-exported in `__all__`); follow that existing asymmetry rather than "fixing" it as a drive-by change.
</critical_notes>

<file_map>
## SERVICES
- `inventory.py` - `OrganizationInventory`: TTL-cached org/network/device/availability/license/login-security data, shared across all collectors via `CollectorManager`.
- `client_store.py` - `ClientStore`: in-memory per-network client cache backing the `/clients` page and `ClientsCollector`.
- `dns_resolver.py` - `DNSResolver`: reverse-DNS hostname lookups for client IPs, with its own TTL cache, used by `ClientsCollector` and the `/clients` page + `POST /api/clients/clear-dns-cache`.
- `status.py` - `StatusService` + `StatusSnapshot`/`CollectorStatus`/`ApiHealthStatus`/`DataFreshnessStatus`/`OrgHealthStatus`/`SystemStatus` dataclasses backing the `/status` health dashboard (`app.py`'s `status()` route, HTML or `?format=json`).
</file_map>

<paved_path>
## INVENTORY CACHE CONTRACT

TTLs (constants on `OrganizationInventory`, seconds): `TTL_FAST=300`, `TTL_MEDIUM=900` (default, set via `set_ttl_for_tier(tier)`), `TTL_SLOW=1800`, `TTL_AVAILABILITY=120` (device availabilities are more dynamic so they get their own shorter TTL regardless of the general `_ttl`), `TTL_LICENSE=1800`, `TTL_CONFIG=3600` (login security). All TTLs get ±10% jitter in `_is_expired()` to avoid thundering-herd refreshes.

```python
# Standard read path — filter applied automatically
networks = await inventory.get_networks(org_id)
devices = await inventory.get_devices(org_id)  # optionally network_id=... to scope further
availabilities = await inventory.get_device_availabilities(org_id)

# Allow-list pattern for collectors that iterate org-wide SDK responses
# directly (not via get_devices) and need to drop rows outside the filter:
allowed_ids = await inventory.get_allowed_network_ids(org_id)
if allowed_ids is not None:
    rows = [r for r in rows if r.get("networkId") in allowed_ids]
```

`get_allowed_network_ids(org_id, *, force_refresh=False)` returns `None` when no filter is
configured (`NetworkFilter.is_active` is False) — treat `None` as "accept every row", not
as "no networks allowed".

Cache invalidation: `await inventory.invalidate(org_id=None)` clears everything; pass an
`org_id` to clear just that organization (used after config changes, not on a normal
collection tick). `warm_cache(org_ids=None)` pre-populates organizations/networks/devices
before the first collection cycle so it hits cache instead of missing on startup.

## DNS / CLIENT STORE INTERPLAY
`DNSResolver.resolve_multiple()` takes `(client_id, ip, description)` tuples, tracks IP
changes per-client via `track_client()` (invalidating the old IP's cache entry on change),
and resolves with a concurrency cap of 5 (`asyncio.Semaphore(5)`). `ClientStore.update_clients()`
takes the resolved `hostnames: dict[str, str | None]` (by IP) and computes
`calculatedHostname = hostname or description or ip or "unknown"` per client — this must
match `ClientsCollector._determine_hostname`'s logic (see the inline comment in
`client_store.py::update_clients`) or client-facing hostnames will disagree between the
`/clients` page and the collector's own metric labels.
</paved_path>
