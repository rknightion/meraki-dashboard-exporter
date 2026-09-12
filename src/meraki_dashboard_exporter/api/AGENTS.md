# Meraki API client

- **Every Dashboard SDK operation goes through `core.api_facade.facade_for(owner).call(operation,
  fn, *args, org_id=..., **kwargs)`.** The facade is the only seam that may cross into the
  synchronous SDK: it acquires the per-org limiter, runs the call on the loop default executor
  (`app.py` installs `AsyncMerakiClient.executor` as it), bounds the whole logical fetch - every
  `total_pages="all"` page included - by `APISettings.per_fetch_deadline_seconds`, meters attempts
  and owns 429 retries. A collector calling `asyncio.to_thread()` or `run_in_executor()` on an SDK
  method itself bypasses all of that and is forbidden.
- Rate limiting is two independent layers, neither hardcoded to 5/s:
  - **429 retries have a single owner.** `_create_api_client()` passes `wait_on_rate_limit=False`,
    so the SDK never sleeps on a 429 inside a worker thread; `MerakiApiFacade.call()` honours a
    `Retry-After` capped at `APISettings.retry_after_max_seconds`, otherwise jittered exponential
    backoff, bounded to `1 + APISettings.max_retries` attempts. The SDK kwarg `maximum_retries`
    still bounds its own connection and 5xx retries.
  - **Client-side pre-throttle:** `core/rate_limiter.py::OrgRateLimiter`, a per-org token bucket the
    facade acquires before every attempt. `APISettings.rate_limit_requests_per_second` 10,
    `rate_limit_burst` 10, `rate_limit_shared_fraction` 0.8 (the remaining 20% of the org budget is
    deliberate headroom for other consumers), `rate_limit_jitter_ratio` 0.1, off via
    `rate_limit_enabled`.
- `MerakiSettings.api_key` is a `SecretStr` and `.get_secret_value()` is called exactly once, in
  `_create_api_client()`.
- `api_base_url` is validated against the known regional origins; any other HTTPS origin needs
  `allow_custom_api_base_url=True`.
- The client class is `AsyncMerakiClient`; there is no `MerakiClient`. `app.py` builds one per
  process and hands collectors its raw `.api` handle, so a collector passes the bound SDK method to
  the facade rather than calling it.
- Not every endpoint accepts `total_pages` (memory-usage history does not), and some wrap results in
  `{"items": [...]}`, which `validate_response_format` unwraps by default.

Canonical fetcher shape:

```python
@with_error_handling(operation="Fetch devices", continue_on_error=True)
@log_api_call("getOrganizationDevices")
async def _fetch_devices(self, org_id: str) -> list[Device]:
    self._track_api_call("getOrganizationDevices")
    raw = await facade_for(self).call(
        "getOrganizationDevices",
        self.api.organizations.getOrganizationDevices,
        org_id,
        org_id=org_id,
        total_pages="all",
    )
    data = validate_response_format(raw, expected_type=list, operation="getOrganizationDevices")
    return [Device.model_validate(d) for d in data]
```
