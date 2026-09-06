# Test suite

- Collector tests inherit `BaseCollectorTest` (`helpers/base.py`), which supplies `settings`,
  `isolated_registry`, `mock_api_builder`, `mock_api`, `rate_limiter`, `collector`, `metrics`,
  `metric_snapshot` and `inventory`. `inventory` is a real `OrganizationInventory` backed by the
  mock API, so assert network reads through it rather than patching `NetworkFilter` out or stubbing
  `getOrganizationNetworks`.
- `AsyncCollectorTestMixin` (same module) adds `collect_with_timeout(collector, timeout=5.0)` and
  `collect_multiple_times(collector, count=3, interval=0.1)`. Mix it in rather than hand-rolling an
  `asyncio.wait_for` around `collector.collect()`.
- Build data with the factories in `helpers/factories.py` and responses with `MockAPIBuilder`
  (`helpers/mock_api.py`). `OrganizationFactory.create()` takes `org_id=`, not `id=`, and
  `DeviceFactory.create(device_type=...)` derives `model` when you do not pass one.
- `with_error(method_name, error, **kwargs)` takes an `Exception` instance or an `int` HTTP status
  code (an int becomes `HTTPError(f"HTTP {code}", code)`). There is no `exception_type=` or
  `message=` kwarg form. Extra kwargs scope the error to a matching call, as with
  `with_custom_response`.

**Do not give a mocked error a rate-limit-shaped message.** `with_error_handling`
(`core/error_handling.py`) matches the message against `RATE_LIMIT_PATTERNS` - "rate limit
exceeded", "too many requests", "throttled", "rate limited" - and then really retries. Its
`max_retries=3` and `base_delay=10.0` are decorator defaults, not settings, so the autouse
`fast_test_settings` fixture (which only sets `MERAKI_EXPORTER_API__MAX_RETRIES=0` and disables
smoothing) does not disable them: roughly 10s + 20s + 40s of real `asyncio.sleep` against
pytest-timeout's `timeout = 30`, so the test dies with an opaque timeout instead of an assertion.
Use a message like `"Connection error"` for generic error paths, or `with_error(method, 429)` with
`asyncio.sleep` patched when the retry path is the point.

## Autouse fixtures worth knowing about

- `default_facade_limiter_for_tests` (`conftest.py`) patches `MerakiApiFacade.__init__` to inject an
  immediate no-delay limiter, so a test that does not build the production owner graph still runs.
  Mark a test `strict_facade_limiter` to opt out and exercise the real fail-closed pacing contract.
  An explicitly supplied limiter double always wins.
- `clean_prometheus_registry` unregisters everything from the global `REGISTRY` before and after
  every test. Assert against the `isolated_registry` fixture, not the global one.
- `force_debug_log_capture` is required to see `logger.debug` in `structlog.testing.capture_logs()`:
  another test's `setup_logging` leaves an INFO-filtering bound logger configured globally, which
  drops debug events before capture sees them.
- `reset_client_auth_state` clears the `AsyncMerakiClient` auth-outcome latch around every test.

## Corpus boundary

Synthetic fleet shapes live in `fixtures/` (`fleet.py` shapes, `fleet_measurement.py` for the
full-runtime measurement entrypoint). Retained real Meraki responses belong only in the fail-closed
`harness/` corpus with its manifest and sanitizer, never in `fixtures/`. Tests never call the live
API; the harness replay server stands in.

A new fetcher needs a test that feeds the SDK exhausted-retry shape (a dict with an `errors` key)
and asserts `validate_response_format` raises `RetryableAPIError` or `DataValidationError`.
