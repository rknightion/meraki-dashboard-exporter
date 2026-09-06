# Services

`OrganizationInventory` is constructed once in `collectors/manager.py::CollectorManager.__init__`
with a live `NetworkFilter(settings.network_filter)` and shared by every collector as
`self.inventory` / `parent.inventory`.

## Inventory cache

- **The cache stores the full, unfiltered API response and applies `NetworkFilter` on every read**
  (`get_networks`, `get_devices`, `get_device_availabilities`), never on write. One org-wide fetch
  therefore serves filtered and unfiltered callers, and `invalidate()` / `force_refresh` stay simple.
- **`get_allowed_network_ids(org_id, *, force_refresh=False)` returns `None` when no filter is
  configured** (`NetworkFilter.is_active` is False). `None` means accept every row, not reject every
  row. It is the allow-list for a collector that iterates an org-wide SDK response directly instead
  of going through `get_devices`:

  ```python
  allowed_ids = await inventory.get_allowed_network_ids(org_id)
  if allowed_ids is not None:
      rows = [r for r in rows if r.get("networkId") in allowed_ids]
  ```

- `unfiltered=True` on `get_networks` / `get_devices` / `get_device_availabilities` is a bounded
  escape hatch for two callers: internal recursive resolution of `allowed_ids` on a cache miss, and
  `CollectorManager._validate_network_filter()` comparing the full and resolved sets at startup. Do
  not add a collector call site.
- TTL constants on the class, in seconds: `TTL_MEDIUM=900` is the general TTL and is fixed for every
  reader (there is no per-collector TTL wiring), `TTL_AVAILABILITY=120` always applies to device
  availabilities regardless of `_ttl`, `TTL_LICENSE=1800`. `_is_expired()` adds +/-10% jitter.
- `invalidate(org_id=None)` clears everything; pass an `org_id` after a config change rather than on
  a collection tick. `warm_cache(org_ids=None)` pre-populates orgs, networks and devices so the
  first cycle hits cache.

## DNS resolver and client store

- `resolve_multiple()` takes `(client_id, ip, description)` tuples and returns hostnames keyed by
  **IP**, not by client id. It runs a bounded queue plus a worker pool sized by
  `ClientSettings.dns_max_concurrent_lookups` (default 32); a semaphore around a whole-list
  `gather` was rejected deliberately, because it still allocates a coroutine per client at the
  25,000-client cap. Resolution batches are sequenced so a slow older batch cannot publish over a
  newer one.
- `ClientStore.update_clients()` computes `calculatedHostname = hostname or description or ip or
  "unknown"`. This must stay identical to `ClientsCollector._determine_hostname`, or the `/clients`
  page and the collector's metric labels disagree about the same client.
- `services/__init__.py` re-exports `ClientStore`, `DNSResolver` and `OrganizationInventory` only.
  `StatusService` is imported from `services.status` directly. That asymmetry is intentional; leave
  it.
