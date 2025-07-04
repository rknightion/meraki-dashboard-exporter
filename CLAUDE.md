# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a prometheus exporter that connects to the Cisco Meraki Dashhboard API and exposes various metrics as a prometheus exporter. It also acts as an opentelementry collector pushing metrics and logs to an OTEL endpoint.

## Development Patterns

We use the Meraki Dashboard Python API from https://github.com/meraki/dashboard-api-python
Meraki Dashboard API Docs are available at https://developer.cisco.com/meraki/api-v1/api-index/
We use UV for all python project management
We use ruff for all python linting
We use ty for all python type checking

### Testing with Builders
```python
# Use builders for test data
device = MerakiDeviceBuilder().with_type("MT").with_name("Test Sensor").build()
sensor_data = SensorDataBuilder().with_temperature(22.5).build()
hub = await HubBuilder().with_device(device).build()
```

### Performance Monitoring
- Use `@performance_monitor` decorator on API methods
- Metrics tracked: `meraki_http_latency_seconds`, `meraki_http_errors_total`
- Circuit breaker pattern for repeated failures

## Code Style

- **Formatting**: Black formatter with 88-char line length
- **Type hints**: Required for all functions
- **Docstrings**: Google style
- **Constants**: Use StrEnum
- **Imports**: Group logically (stdlib, third-party, local)
- **Early returns**: Reduce nesting

## API Guidelines

- Use Meraki Python SDK (never direct HTTP)
- Configure with `suppress_logging=True`
- Use `total_pages='all'` for pagination
- Implement tiered refresh intervals:
  - Static data: 4 hours
  - Semi-static: 1 hour
  - Dynamic: 5-10 minutes

## Home Assistant Conventions

- Use update coordinators for data fetching
- Proper error handling (ConfigEntryAuthFailed, ConfigEntryNotReady)
- Physical devices = HA devices, metrics = entities
- Implement proper unique IDs and device identifiers
- Follow HA entity naming conventions

## Common Tasks

### Debug API Calls
```python
# Add logging to debug API responses
_LOGGER.debug("API response: %s", response)
```

### Add New Sensor Type
0. Validate API calls against the Meraki Dashboard API docs available from https://developer.cisco.com/meraki/api-v1
1. Add to device sensor descriptions
2. Update data transformer
3. Add icon mapping in factory
4. Write unit tests

### Handle Missing Data
```python
# Use get() with defaults
value = data.get("temperature", {}).get("value")
if value is not None:
    # Process value
```

## Important Files

- `coordinator.py`: Main update coordinator
- `entities/factory.py`: Entity creation logic
- `config/schemas.py`: Configuration data classes
- `data/transformers.py`: API response processing
- `utils/error_handling.py`: Error handling utilities
