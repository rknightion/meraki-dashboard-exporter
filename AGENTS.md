# AGENTS.md

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
- `docs/` - Documentation including ADRs and metrics reference
</file_map>

<paved_path>
## HIGH-LEVEL ARCHITECTURE

### Collector Organization
- **Core Infrastructure**: Logging, config, metrics, error handling → `src/meraki_dashboard_exporter/core/CLAUDE.md`
- **Collector Pattern**: Auto-registration, update tiers, base classes → `src/meraki_dashboard_exporter/collectors/CLAUDE.md`
- **Device-Specific**: MR, MS, MX, MT, MG, MV collectors → `src/meraki_dashboard_exporter/collectors/devices/CLAUDE.md`
- **API Integration**: Async wrapper for Meraki SDK → `src/meraki_dashboard_exporter/api/CLAUDE.md`
- **Testing**: Factories, mocks, assertions → `tests/CLAUDE.md`

### Key Principles
- **Enum-based naming**: Use MetricName and LabelName enums for consistency
- **Domain models**: Pydantic validation for all API responses
- **Error handling**: Decorators for consistent error management
- **Update tiers**: FAST (60s), MEDIUM (300s), SLOW (900s) based on volatility
</paved_path>

<workflow>
## PROJECT-WIDE WORKFLOW
Navigate to specific subdirectories for detailed implementation patterns:

### Development Areas
- **Core Changes**: Infrastructure, logging, config → `src/meraki_dashboard_exporter/core/CLAUDE.md`
- **New Collectors**: Device, organization, network health → `src/meraki_dashboard_exporter/collectors/CLAUDE.md`
- **API Updates**: Client wrapper changes → `src/meraki_dashboard_exporter/api/CLAUDE.md`
- **Testing**: New tests, factories, mocks → `tests/CLAUDE.md`

### Cross-Cutting Concerns
- **Metrics**: Always use enums from `core/constants/metrics_constants.py`
- **Labels**: Always use `LabelName` enum from `core/metrics.py`
- **Domain Models**: Always validate with Pydantic models
- **Error Handling**: Always use decorators from `core/error_handling.py`
</workflow>

<bash_commands>
## COMMON COMMANDS
- `uv run python -m meraki_dashboard_exporter` - Start the exporter
- `uv run ruff check --fix .` - Lint and auto-fix code
- `uv run mypy .` - Type checking
- `uv run pytest` - Run tests
- `uv run pytest -v -k test_name` - Run specific test
- `uv run python src/meraki_dashboard_exporter/tools/generate_metrics_docs.py` - Generate metrics docs
- `uv add package_name` - Add new dependency
- `docker-compose up` - Start with Docker
- `make docs-serve` - Serve documentation locally
</bash_commands>

<code_style>
## PROJECT-WIDE STYLE GUIDELINES
- **Formatting**: Black with 88-char line length
- **Type hints**: Use `from __future__ import annotations` and proper typing
- **Imports**: Group stdlib, third-party, local with proper organization
- **Docstrings**: NumPy-style with type hints
- **Constants**: Use Literal & Enum/StrEnum appropriately
- **Early returns**: Reduce nesting where possible
- **Async**: Use `asyncio.to_thread()` for Meraki SDK calls
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
</fatal_implications>

<hatch>
## ALTERNATIVE APPROACHES
When the paved path doesn't fit, see subdirectory `CLAUDE.md` files for:
- **Core Alternatives**: Custom metrics, error recovery → `src/meraki_dashboard_exporter/core/CLAUDE.md`
- **Collector Variations**: Alternative registration, custom patterns → `src/meraki_dashboard_exporter/collectors/CLAUDE.md`
- **API Workarounds**: Fallback strategies, custom endpoints → `src/meraki_dashboard_exporter/api/CLAUDE.md`
- **Testing Strategies**: Custom mocks, specialized assertions → `tests/CLAUDE.md`
</hatch>
