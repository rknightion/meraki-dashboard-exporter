<system_context>
Meraki Dashboard Exporter Test Suite - Comprehensive testing infrastructure with factories, mocks, and assertions for validating collector behavior, API interactions, and metric generation.
</system_context>

<critical_notes>
- **Inherit from `BaseCollectorTest`** for automatic fixture setup
- **Use test factories** from `helpers/factories.py` for consistent test data
- **Mock with `MockAPIBuilder`** for cleaner API response mocking
- **Assert metrics** with `MetricAssertions` for clear verification
- **Test error scenarios** with `.with_error()` method on mocks
</critical_notes>

<file_map>
## TEST ORGANIZATION
- `conftest.py` - Pytest configuration and shared fixtures
- `helpers/` - Test utilities and support classes:
  - `base.py` - `BaseCollectorTest` with common test patterns
  - `factories.py` - Data factories for creating realistic test data
  - `mock_api.py` - `MockAPIBuilder` for API response mocking
  - `metrics.py` - `MetricAssertions` for metric validation
  - `large_org_fixture.py` - Large organization test fixture
- `fixtures/` - Test fixture definitions:
  - `large_org.py` - Large organization fixture data
- `unit/` - Unit tests for individual components:
  - 25+ test modules for core, collectors, services
  - `collectors/` - Device-specific collector tests (`test_mr_collector.py`, `test_ms_collector.py`, `test_ms_stack_collector.py`, `test_mx_collector.py`, `test_mx_firewall_collector.py`, `test_mx_vpn_collector.py`, `test_mv_collector.py`, `test_mg_collector.py`, `test_ssid_performance_collector.py`)
- `integration/` - Integration tests:
  - `test_collection_cycle.py`
  - `test_collector_manager_integration.py`
  - `test_metric_expiration.py`
  - `test_metrics_integration.py`
- Root-level test files: `test_api_client.py`, `test_config.py`, `test_error_handling.py`, `test_inventory_service.py`, `test_managed_task_group.py`, `test_metrics.py`, `test_webhook.py`, `test_webhook_handler.py`, `test_large_org_fixture.py`
</file_map>

<paved_path>
## BASE TEST PATTERN
```python
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import DeviceFactory, OrganizationFactory

class TestMyCollector(BaseCollectorTest):
    async def test_basic_operation(self, collector, mock_api_builder, metrics):
        org = OrganizationFactory.create()
        devices = DeviceFactory.create_many(3, product_type="MR")

        mock_api_builder.with_organizations([org]).with_devices(devices)
        await self.run_collector(collector)

        metrics.assert_gauge_exists("meraki_device_up")
        metrics.assert_gauge_value("meraki_device_up", 1, serial=devices[0]["serial"])

    async def test_api_error_handling(self, collector, mock_api_builder, metrics):
        org = OrganizationFactory.create()
        mock_api_builder.with_organizations([org]).with_error(
            "getOrganizationDevices",
            exception_type="APIError",
            message="Rate limit exceeded",
        )
        await self.run_collector(collector)
        metrics.assert_no_gauge_exists("meraki_device_up")
```

## FACTORY USAGE
```python
device = DeviceFactory.create(serial="Q2XX-XXXX-XXXX", product_type="MR")
devices = DeviceFactory.create_many(5, product_type="MS")
org = OrganizationFactory.create(id="123456", name="Test Org")
```

## MOCK API CONFIGURATION
```python
mock_api_builder.with_organizations([org]).with_devices(devices)
mock_api_builder.with_custom_response("getOrganizationWirelessDevicesChannelUtilization", [...])
mock_api_builder.with_error("getOrganizationDevices", exception_type="ConnectionError")
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
