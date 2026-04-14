# CLAUDE.md

<system_context>
Meraki Dashboard Exporter - A production-ready Prometheus exporter that collects metrics from Cisco Meraki Dashboard API and exposes them for monitoring. Supports OpenTelemetry mirroring and includes comprehensive collectors for devices, networks, organizations, and sensor data.
</system_context>

<critical_notes>
- **Navigate to subdirectories** for detailed context - each has its own `CLAUDE.md`
- **Follow update tiers**: FAST (60s), MEDIUM (300s), SLOW (900s) based on data volatility
- **Security**: Never log or expose API keys, use read-only when possible
- **Memory**: Be mindful of API rate limits and implement proper error handling
- **Use parallel tasks/agents** when suitable use the parallel tasks and agents available to you
- **Never issue git commands** the user will handle all 'git' commands
</critical_notes>

<file_map>
## NAVIGATION MAP - DETAILED CONTEXT IN SUBDIRECTORIES
- `src/meraki_dashboard_exporter/` - Main source package - See `src/meraki_dashboard_exporter/CLAUDE.md`
- `src/meraki_dashboard_exporter/core/` - Core infrastructure - See `src/meraki_dashboard_exporter/core/CLAUDE.md`
- `src/meraki_dashboard_exporter/collectors/` - Collector implementations - See `src/meraki_dashboard_exporter/collectors/CLAUDE.md`
- `src/meraki_dashboard_exporter/collectors/devices/` - Device collectors - See `src/meraki_dashboard_exporter/collectors/devices/CLAUDE.md`
- `src/meraki_dashboard_exporter/collectors/organization_collectors/` - Organization collectors - See `src/meraki_dashboard_exporter/collectors/organization_collectors/CLAUDE.md`
- `src/meraki_dashboard_exporter/collectors/network_health_collectors/` - Network health - See `src/meraki_dashboard_exporter/collectors/network_health_collectors/CLAUDE.md`
- `src/meraki_dashboard_exporter/api/` - API client wrapper - See `src/meraki_dashboard_exporter/api/CLAUDE.md`
- `tests/` - Test suite and patterns - See `tests/CLAUDE.md`
- `pyproject.toml` - Project dependencies and configuration
- `dashboards/` - Grafana dashboard JSON exports
- `docs/` - MkDocs documentation site
- `scripts/` - Code generation and documentation scripts
</file_map>

<paved_path>
## HIGH-LEVEL ARCHITECTURE

### Collector Organization
- **Core Infrastructure**: Logging, config, metrics, error handling -> `src/meraki_dashboard_exporter/core/CLAUDE.md`
- **Collector Pattern**: Auto-registration, update tiers, base classes -> `src/meraki_dashboard_exporter/collectors/CLAUDE.md`
- **Device-Specific**: MR, MS, MX, MT, MG, MV collectors -> `src/meraki_dashboard_exporter/collectors/devices/CLAUDE.md`
- **API Integration**: Async wrapper for Meraki SDK -> `src/meraki_dashboard_exporter/api/CLAUDE.md`
- **Testing**: Factories, mocks, assertions -> `tests/CLAUDE.md`

### Key Principles
- **Domain-specific metric enums**: Use `OrgMetricName`, `DeviceMetricName`, `MSMetricName`, `MRMetricName`, etc. from `core/constants/metrics_constants.py`
- **Label enums**: Use `LabelName` enum from `core/metrics.py`
- **Domain models**: Pydantic validation for all API responses
- **Error handling**: Decorators from `core/error_handling.py`
- **Update tiers**: FAST (60s), MEDIUM (300s), SLOW (900s) based on volatility
- **Parallel collection**: Use `ManagedTaskGroup` for bounded concurrency
- **Inventory caching**: Leverage shared `OrganizationInventory` service to reduce API calls
- **Metric lifecycle**: Track and expire metrics for offline/removed devices

</paved_path>

<bash_commands>
## COMMON COMMANDS
- `uv run python -m meraki_dashboard_exporter` - Start the exporter
- `uv run ruff check --fix .` - Lint and auto-fix code
- `uv run ruff format .` - Format code
- `uv run mypy .` - Type checking
- `uv run pytest` - Run tests
- `uv run pytest -v -k test_name` - Run specific test
- `uv add package_name` - Add new dependency
- `make check` - Run all checks (lint, typecheck, test)
- `make docgen` - Generate all documentation
- `make docker-compose-up` - Start with Docker
- `make run-dev` - Run with auto-reload for development
</bash_commands>

<code_style>
## PROJECT-WIDE STYLE GUIDELINES
- **Formatting**: Ruff with 100-char line length (target: py314)
- **Type hints**: Use `from __future__ import annotations` and proper typing
- **Imports**: Relative imports within package (e.g., `from ..core.metrics import LabelName`)
- **Docstrings**: NumPy-style with type hints
- **Constants**: Use StrEnum for metric/label names
- **Early returns**: Reduce nesting where possible
- **Async**: Use `asyncio.to_thread()` for Meraki SDK calls (SDK is synchronous)
</code_style>

<fatal_implications>
## PROJECT-WIDE CRITICAL "DO NOT" RULES
- **NEVER use hardcoded metric/label names** - always use enums
- **NEVER log API keys or sensitive data**
- **NEVER assume API response format** - always validate
- **NEVER skip error handling** for API calls
- **NEVER use `any` types** without explicit justification
- **NEVER modify tests to match incorrect implementations**
- **NEVER commit without running linters and type checks**
- **NEVER work in subdirectories without consulting their `CLAUDE.md`**
- **NEVER use unbounded parallelism** - always use ManagedTaskGroup with max_concurrency
- **NEVER bypass inventory service** - use cached data when available
- **NEVER forget metric tracking** - use `parent._set_metric()` for automatic expiration
</fatal_implications>
