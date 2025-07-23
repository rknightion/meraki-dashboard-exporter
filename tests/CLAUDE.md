<system_context>
Meraki Dashboard Exporter Test Suite - Comprehensive testing infrastructure with factories, mocks, and assertions for validating collector behavior, API interactions, and metric generation.
</system_context>

<critical_notes>
- **Inherit from BaseCollectorTest** for automatic fixture setup
- **Use test factories** from `helpers/factories.py` for consistent test data
- **Mock with MockAPIBuilder** for cleaner API response mocking
- **Assert metrics** with MetricAssertions for clear verification
- **Test error scenarios** with `.with_error()` method on mocks
</critical_notes>

<file_map>
## TEST ORGANIZATION
- `conftest.py` - Pytest configuration and shared fixtures
- `helpers/` - Test utilities and support classes
  - `factories.py` - Data factories for creating realistic test data
  - `mock_api.py` - MockAPIBuilder for API response mocking
  - `metrics.py` - MetricAssertions for metric validation
  - `base.py` - BaseCollectorTest with common test patterns
- `unit/` - Unit tests for individual components
- `integration/` - Integration tests for end-to-end scenarios
- `test_config.py` - Configuration and environment testing
</file_map>

<paved_path>
## BASE TEST PATTERN
```python
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import DeviceFactory, OrganizationFactory
from tests.helpers.mock_api import MockAPIBuilder

class TestMyCollector(BaseCollectorTest):
    """Test MyCollector with standard patterns"""

    async def test_collector_basic_operation(self, collector, mock_api_builder, metrics):
        # Setup test data with factories
        org = OrganizationFactory.create()
        devices = DeviceFactory.create_many(3, product_type="MR")

        # Configure API mocks
        mock_api_builder.with_organizations([org]).with_devices(devices)

        # Run collector
        await self.run_collector(collector)

        # Assert metrics were created
        metrics.assert_gauge_exists("meraki_device_up")
        metrics.assert_gauge_value("meraki_device_up", 1, serial=devices[0]["serial"])
```

## ERROR TESTING PATTERN
```python
async def test_collector_api_error_handling(self, collector, mock_api_builder, metrics):
    # Setup error scenario
    org = OrganizationFactory.create()
    mock_api_builder.with_organizations([org]).with_error(
        "getOrganizationDevices",
        exception_type="APIError",
        message="Rate limit exceeded"
    )

    # Run collector - should handle error gracefully
    await self.run_collector(collector)

    # Verify error handling
    metrics.assert_no_gauge_exists("meraki_device_up")
```
</paved_path>

<patterns>
## TESTING STRATEGIES

### Data Factory Usage
```python
# Create single realistic device
device = DeviceFactory.create(
    serial="Q2XX-XXXX-XXXX",
    product_type="MR",
    name="Office AP"
)

# Create multiple devices with variations
devices = DeviceFactory.create_many(5, product_type="MS")

# Create organization with specific attributes
org = OrganizationFactory.create(
    id="123456",
    name="Test Organization"
)
```

### API Mock Configuration
```python
# Basic mock setup
mock_api_builder.with_organizations([org]).with_devices(devices)

# Add specific API responses
mock_api_builder.with_custom_response(
    "getOrganizationWirelessDevicesChannelUtilization",
    [{"serial": "Q2XX-XXXX-XXXX", "utilization": 45.2}]
)

# Configure error scenarios
mock_api_builder.with_error(
    "getOrganizationDevices",
    exception_type="ConnectionError"
)
```

### Metric Assertions
```python
# Check metric exists
metrics.assert_gauge_exists("meraki_device_up")

# Check specific metric value
metrics.assert_gauge_value("meraki_device_up", 1, org_id="123", serial="Q2XX-XXXX-XXXX")

# Check metric does not exist
metrics.assert_no_gauge_exists("invalid_metric")

# Check metric with partial labels
metrics.assert_gauge_value("meraki_channel_utilization", 45.2, serial="Q2XX-XXXX-XXXX")
```
</patterns>

<examples>
## Complete Test Class Example
```python
import pytest
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import DeviceFactory, OrganizationFactory
from tests.helpers.mock_api import MockAPIBuilder
from src.meraki_dashboard_exporter.collectors.devices.mr import MRCollector

class TestMRCollector(BaseCollectorTest):
    """Test MR (Wireless) device collector"""

    @pytest.fixture
    def collector_class(self):
        return MRCollector

    async def test_channel_utilization_collection(self, collector, mock_api_builder, metrics):
        """Test collection of wireless channel utilization metrics"""
        # Setup test data
        org = OrganizationFactory.create(id="123456")
        mr_devices = DeviceFactory.create_many(2, product_type="MR")

        # Mock channel utilization response
        channel_data = [
            {
                "serial": mr_devices[0]["serial"],
                "byBand": [
                    {"band": "2.4", "utilization": {"average": 25.5}},
                    {"band": "5", "utilization": {"average": 15.2}}
                ]
            },
            {
                "serial": mr_devices[1]["serial"],
                "byBand": [
                    {"band": "2.4", "utilization": {"average": 45.8}},
                    {"band": "5", "utilization": {"average": 32.1}}
                ]
            }
        ]

        # Configure mocks
        mock_api_builder.with_organizations([org]) \
                       .with_devices(mr_devices) \
                       .with_custom_response(
                           "getOrganizationWirelessDevicesChannelUtilization",
                           channel_data
                       )

        # Run collector
        await self.run_collector(collector)

        # Assert metrics were created correctly
        metrics.assert_gauge_exists("meraki_channel_utilization")

        # Check specific values
        metrics.assert_gauge_value(
            "meraki_channel_utilization",
            25.5,
            org_id="123456",
            serial=mr_devices[0]["serial"],
            band="2.4"
        )

        metrics.assert_gauge_value(
            "meraki_channel_utilization",
            15.2,
            org_id="123456",
            serial=mr_devices[0]["serial"],
            band="5"
        )

    async def test_api_error_handling(self, collector, mock_api_builder, metrics):
        """Test graceful handling of API errors"""
        org = OrganizationFactory.create()

        # Configure API to return error
        mock_api_builder.with_organizations([org]) \
                       .with_error(
                           "getOrganizationDevices",
                           exception_type="APIError",
                           message="Rate limit exceeded"
                       )

        # Collector should handle error gracefully
        await self.run_collector(collector)

        # No metrics should be created on error
        metrics.assert_no_gauge_exists("meraki_channel_utilization")

    async def test_empty_device_list(self, collector, mock_api_builder, metrics):
        """Test behavior with no MR devices"""
        org = OrganizationFactory.create()

        # No devices returned
        mock_api_builder.with_organizations([org]).with_devices([])

        # Should complete without error
        await self.run_collector(collector)

        # No metrics should be created
        metrics.assert_no_gauge_exists("meraki_channel_utilization")
```

## Factory Usage Example
```python
# Create realistic sensor reading data
sensor_reading = SensorReadingFactory.create(
    serial="Q2XX-XXXX-XXXX",
    temperature=23.5,
    humidity=45.2,
    timestamp="2024-01-15T10:30:00Z"
)

# Create multiple organizations for multi-org testing
orgs = OrganizationFactory.create_many(3)

# Create devices with specific network assignment
network_devices = DeviceFactory.create_many(
    5,
    network_id="N_123456789",
    product_type="MS"
)
```
</examples>

<workflow>
## WRITING NEW TESTS
1. **Inherit from BaseCollectorTest**: Provides fixtures and common patterns
2. **Use appropriate factory**: Create realistic test data with factories
3. **Mock API responses**: Use MockAPIBuilder for clean API mocking
4. **Test positive path**: Verify normal operation with expected metrics
5. **Test error scenarios**: Use `.with_error()` to test error handling
6. **Test edge cases**: Empty data, malformed responses, etc.
7. **Assert metrics**: Use MetricAssertions for clear metric validation
8. **Test isolation**: Ensure tests don't interfere with each other
</workflow>

<common_tasks>
## DEBUGGING FAILED TESTS
1. **Check factory data**: Verify test data matches expectations
2. **Inspect API mocks**: Ensure mocks return expected data format
3. **Review metric assertions**: Check label names and values match exactly
4. **Add debug logging**: Use `pytest -s` to see log output
5. **Isolate test**: Run single test to eliminate interference
6. **Check fixtures**: Verify collector and mock setup is correct
</common_tasks>

<api_quirks>
## TESTING API SPECIFIC BEHAVIORS
- **Mock pagination**: Some tests need `total_pages="all"` behavior
- **Response formats**: Test both array and wrapped object responses
- **Error scenarios**: Mock rate limits, timeouts, and API errors
- **Timespan constraints**: Test endpoints with specific timespan requirements
- **Product filtering**: Verify `product_types` parameter handling
</api_quirks>

<fatal_implications>
- **NEVER use real API keys** in tests - always use mocks
- **NEVER test against live API** - use MockAPIBuilder exclusively
- **NEVER skip error testing** - API failures are common
- **NEVER assume test isolation** - use proper setup/teardown
- **NEVER hardcode test data** - use factories for consistency
</fatal_implications>
