<system_context>
Meraki Dashboard Exporter Test Suite - Comprehensive testing infrastructure with factories, mocks, and assertions for validating collector behavior, API interactions, and metric generation.
</system_context>

<critical_notes>
- **Inherit from `BaseCollectorTest`** for automatic fixture setup
- **Use test factories** from `helpers/factories.py` for consistent test data
- **Mock with `MockAPIBuilder`** for cleaner API response mocking
- **Assert metrics** with `MetricAssertions` for clear verification
- **Test error scenarios** with `.with_error()` method on mocks
- **Network filter coverage**: When testing collectors that read networks, prefer asserting against the inventory (`OrganizationInventory.get_networks`) so `NetworkFilter` behavior is exercised end-to-end. Tests must not patch out the filter or call `getOrganizationNetworks` directly.
- **Validate-response-format coverage**: For new fetchers, add a test that simulates the SDK exhausted-retry error shape (a dict with an `errors` key) and asserts `validate_response_format` raises `RetryableAPIError`/`DataValidationError` as appropriate.
</critical_notes>

<file_map>
## TEST ORGANIZATION
- `conftest.py` - Shared fixtures: `fast_test_settings` (disables retry/smoothing), `clean_prometheus_registry` (autouse, wipes the global `REGISTRY` before/after every test), `isolated_registry`. Registers `tests.fixtures.large_org` as a pytest plugin.
- `helpers/` - Test utilities and support classes (all re-exported from `helpers/__init__.py`):
  - `base.py` - `BaseCollectorTest` (fixtures: `settings`, `isolated_registry`, `mock_api_builder`, `mock_api`, `collector`, `metrics`, `metric_snapshot`, **`inventory`** — a real `OrganizationInventory` backed by the mock API, so network-filter behavior is exercised) and `AsyncCollectorTestMixin` (`collect_with_timeout`, `collect_multiple_times`)
  - `factories.py` - `DataFactory`, `OrganizationFactory`, `NetworkFactory`, `DeviceFactory` (+ `create_mr`/`create_ms`/`create_mx`/`create_mt`/`create_mixed`), `DeviceStatusFactory`, `AlertFactory`, `SensorDataFactory`, `TimeSeriesFactory`, `ResponseFactory`
  - `mock_api.py` - `MockAPIBuilder` (fluent, builds a `MagicMock` API client) and `MockAsyncIterator`
  - `metrics.py` - `MetricAssertions`, plus `MetricSnapshot`/`MetricDiff` for before/after delta assertions
  - `large_org_fixture.py` - `LargeOrgFixture` + `LargeOrgScenario` (named scale scenarios: `SMALL_ENTERPRISE` 250 devices, `MEDIUM_ENTERPRISE` 1000, `LARGE_ENTERPRISE` 2500, `MULTI_ORG_SMALL` 1000/5 orgs, `MULTI_ORG_LARGE` 10000/10 orgs) for perf/scale testing
- `fixtures/large_org.py` - Pytest-plugin fixtures wrapping `LargeOrgFixture` scenarios: `small_enterprise_fixture`, `medium_enterprise_fixture`, `large_enterprise_fixture`, `multi_org_small_fixture`, `multi_org_large_fixture`, `custom_large_org` (factory fixture for bespoke sizing)
- `unit/` - 49 unit test modules (50 files incl. `__init__.py`) covering core infra and collectors, e.g.:
  - Collectors: `test_alerts_collector.py`, `test_api_usage_collector.py`, `test_client_overview_collector.py`, `test_clients_collector.py`, `test_clients_collector_enhanced.py`, `test_device_collector.py`, `test_license_collector.py`, `test_mt_collector.py`, `test_mt_collector_factory.py`, `test_mt_alerts_collector.py`, `test_mt_gateway_connections.py`, `test_network_health_collector.py`, `test_org_health.py`, `test_organization_collector.py`, `test_firmware_collector.py`, `test_device_availability_history_collector.py`, `test_config_admins_collector.py`, `test_collection_utilization.py`
  - Core/infra: `test_api_helpers.py`, `test_api_models.py`, `test_async_edge_cases.py`, `test_async_utils.py`, `test_batch_processing.py`, `test_cache_cleanup.py`, `test_cardinality_controls.py`, `test_collector_base.py`, `test_config_logger.py`, `test_discovery_service.py`, `test_dns_resolver.py`, `test_domain_models.py`, `test_error_scenarios.py`, `test_exception_syntax.py`, `test_exemplars.py`, `test_inventory_cache_improvements.py`, `test_logging_decorators.py`, `test_logging_helpers.py`, `test_main_entrypoint.py`, `test_metrics_constants.py`, `test_otel_tracing.py`, `test_per_tier_concurrency.py`, `test_registry.py`, `test_span_metrics.py`, `test_subcollector_mixin.py`, `test_webhook_metrics.py`
  - Web/app: `test_app_endpoints.py`, `test_readiness_endpoint.py`, `test_status_endpoint.py`, `test_status_service.py`, `test_client_store.py`
  - `collectors/` - 15 device-specific collector tests: `test_mr_collector.py`, `test_ms_collector.py`, `test_ms_power_collector.py`, `test_ms_stack_collector.py`, `test_mx_collector.py`, `test_mx_firewall_collector.py`, `test_mx_vpn_collector.py`, `test_mx_ha_collector.py`, `test_mx_uplink_usage_collector.py`, `test_mx_uplink_health_collector.py`, `test_mv_collector.py`, `test_mg_collector.py`, `test_ssid_performance_collector.py`, `test_latency_stats_collector.py`, `test_air_marshal_collector.py` (no `__init__.py` in this dir - pytest rootdir-relative discovery still finds it)
- `integration/` - Integration tests:
  - `test_collection_cycle.py`
  - `test_collector_manager_integration.py`
  - `test_metric_expiration.py`
  - `test_metrics_integration.py`
- Root-level test files: `test_api_client.py`, `test_config.py`, `test_error_handling.py`, `test_inventory_service.py`, `test_large_org_fixture.py`, `test_managed_task_group.py`, `test_metrics.py`, `test_webhook.py`, `test_webhook_handler.py`, and the **network-filter suite**: `test_network_filter.py` (resolver logic), `test_network_filter_settings.py` (config model), `test_network_filter_integration.py` (end-to-end with inventory), `test_startup_filter.py` (fail-fast startup validation)
</file_map>

<paved_path>
## BASE TEST PATTERN
```python
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import DeviceFactory, OrganizationFactory

class TestMyCollector(BaseCollectorTest):
    collector_class = MyCollector
    update_tier = UpdateTier.MEDIUM

    async def test_basic_operation(self, collector, mock_api_builder, metrics):
        org = OrganizationFactory.create()
        devices = DeviceFactory.create_many(3, device_type="MR")

        mock_api_builder.with_organizations([org]).with_devices(devices, org_id=org["id"])
        await self.run_collector(collector)

        metrics.assert_metric_exists("meraki_device_up")
        metrics.assert_gauge_value("meraki_device_up", 1, serial=devices[0]["serial"])

    async def test_api_error_handling(self, collector, mock_api_builder, metrics):
        org = OrganizationFactory.create()
        mock_api_builder.with_organizations([org]).with_error(
            "getOrganizationDevices", Exception("Connection error")
        )
        await self.run_collector(collector)
        metrics.assert_metric_not_set("meraki_device_up")
```
Note: `collector`/`mock_api`/`metrics` come from `BaseCollectorTest` fixtures; `with_error`'s
2nd arg is an `Exception` instance or an `int` HTTP status code (404/429 get specific canned
bodies, any other code gets a generic `HTTPError`) - there is no `exception_type=`/`message=`
kwarg form.

**Caution - don't inject a "rate limit" message:** `with_error_handling`'s retry logic
(`core/error_handling.py`) matches error messages against `RATE_LIMIT_PATTERNS` (substrings like
"rate limit exceeded", "too many requests") independently of any test settings, and the retry
knobs (`max_retries=3`, `base_delay=10.0`) are decorator parameters, not settings-driven -
`fast_test_settings` does NOT disable them. An error whose message matches triggers real
`asyncio.sleep` retries (~10s/20s/40s = ~70s total), which blows past pytest-timeout's 30s
(`pyproject.toml`) and kills the test with an opaque timeout instead of a useful assertion
failure. Use a non-rate-limit message (e.g. `"Connection error"`) for generic error-path tests,
or an `int` HTTP status code via `with_error(method, 429)` if you specifically need to exercise
the rate-limit/retry path (and patch `asyncio.sleep` in that case).

## FACTORY USAGE
```python
device = DeviceFactory.create(serial="Q2XX-XXXX-XXXX", device_type="MR")  # model auto-derived
devices = DeviceFactory.create_many(5, device_type="MS")
org = OrganizationFactory.create(org_id="123456", name="Test Org")  # kwarg is `org_id`, not `id`
```

## MOCK API CONFIGURATION
```python
mock_api_builder.with_organizations([org]).with_devices(devices, org_id=org["id"])
mock_api_builder.with_custom_response("getOrganizationWirelessDevicesChannelUtilization", [...])
mock_api_builder.with_error("getOrganizationDevices", Exception("Connection error"))
mock_api_builder.with_error("getNetworkWirelessConnectionStats", 404)  # int -> canned HTTPError
```
</paved_path>

<workflow>
## WRITING NEW TESTS
1. **Inherit from `BaseCollectorTest`**: Provides fixtures and common patterns
2. **Use factories**: Create realistic test data
3. **Mock API**: Use `MockAPIBuilder` for clean API mocking
4. **Test positive path**: Verify normal operation with expected metrics
5. **Test error scenarios**: Use `.with_error()` for error handling tests
6. **Test edge cases**: Empty data, malformed responses, etc.
7. **Assert metrics**: Use `MetricAssertions` for clear validation
</workflow>

<fatal_implications>
- **NEVER use real API keys** in tests - always use mocks
- **NEVER test against live API** - use `MockAPIBuilder` exclusively
- **NEVER skip error testing** - API failures are common
- **NEVER hardcode test data** - use factories for consistency
</fatal_implications>
