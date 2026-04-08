<system_context>
Meraki Dashboard Exporter - Main source package containing core infrastructure, collectors, API client, and application entry points.
</system_context>

<critical_notes>
- **Entry point**: `app.py` for FastAPI application, `__main__.py` for CLI
- **Import structure**: Always use relative imports within package
- **Type safety**: Package includes `py.typed` marker for mypy compatibility
</critical_notes>

<file_map>
## PACKAGE STRUCTURE
- `core/` - Core infrastructure (logging, config, models, metrics, error handling, OTel) - See `core/CLAUDE.md`
- `collectors/` - All metric collectors and collection logic - See `collectors/CLAUDE.md`
- `api/` - Meraki API client wrapper - See `api/CLAUDE.md`
- `services/` - Supporting services:
  - `inventory.py` - Shared organization/device/network cache with TTL-based invalidation
  - `client_store.py` - Client data storage
  - `dns_resolver.py` - DNS resolution service
- `models/` - Shared data models (`webhook.py`)
- `templates/` - HTML templates for web UI (index, cardinality, clients pages)
- `app.py` - FastAPI application with web UI and metrics endpoint
- `__main__.py` - CLI entry point for running the exporter
- `__version__.py` - Version information (reads from pyproject.toml)
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
