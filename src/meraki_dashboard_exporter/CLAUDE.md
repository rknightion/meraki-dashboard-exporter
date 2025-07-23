<system_context>
Meraki Dashboard Exporter - Main source package containing core infrastructure, collectors, API client, and application entry points. This is the heart of the Prometheus exporter system.
</system_context>

<critical_notes>
- **Entry point**: Use `app.py` for FastAPI application, `__main__.py` for CLI
- **Import structure**: Always import from relative paths within package
- **Type safety**: Package includes `py.typed` marker for mypy compatibility
</critical_notes>

<file_map>
## PACKAGE STRUCTURE
- `core/` - Core infrastructure (logging, config, models, metrics) - See `core/CLAUDE.md`
- `collectors/` - All metric collectors and collection logic - See `collectors/CLAUDE.md`
- `api/` - Meraki API client wrapper - See `api/CLAUDE.md`
- `services/` - Supporting services (DNS, client store)
- `models/` - Shared data models (currently minimal)
- `templates/` - HTML templates for web UI
- `tools/` - Code generation and documentation tools
- `utils/` - General utilities
- `app.py` - FastAPI application with web UI and metrics endpoint
- `__main__.py` - CLI entry point for running the exporter
- `__version__.py` - Version information
</file_map>

<paved_path>
## ENTRY POINTS
```python
# CLI usage
python -m meraki_dashboard_exporter

# Programmatic usage
from meraki_dashboard_exporter.app import create_app
app = create_app()
```
</paved_path>

<example>
Adding a new service:
```python
# src/meraki_dashboard_exporter/services/my_service.py
from ..core.logging import get_logger

logger = get_logger(__name__)

class MyService:
    def __init__(self):
        logger.info("Service initialized")
```
</example>
