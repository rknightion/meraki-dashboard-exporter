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
- `services/` - Supporting services (`OrganizationInventory`, `ClientStore`, `DNSResolver`, `StatusService`) - See `services/CLAUDE.md`
- `models/` - Shared Pydantic data models: `webhook.py` (`WebhookPayload`, alias-based camelCase mapping for the raw Meraki webhook JSON)
- `templates/` - Jinja2 HTML templates for the web UI, wired via `Jinja2Templates`/`TemplateResponse` in `app.py`: `index.html` (landing page + collector table + manual-trigger button), `status.html` (`/status` health dashboard), `clients.html` (`/clients` page + DNS-cache-clear button), `cardinality.html`, `cardinality_all_labels.html`, `cardinality_all_metrics.html` (cardinality drill-down pages, served by `core/cardinality.py`'s `setup_cardinality_endpoint`). Each template is a fully self-contained file (inline `<style>`/`<script>`, no `{% extends %}`/`{% include %}`/macros, no shared base or asset build step) — edit each page directly.
- `app.py` - `ExporterApp`: builds `FastAPI` app via `create_app()`/`ExporterApp.create_app()`. Owns the `lifespan` (runs `DiscoveryService`, starts `MetricExpirationManager`, kicks off `_startup_collections`/per-collector group-clocked loops (`_collector_loop`), periodic cardinality analysis) and registers routes: `/` (index), `/health`, `/ready` (readiness gated on every collector owning an enabled priority<=3 endpoint group; priority-4 config-only collectors excluded), `/metrics`, `/clients`, `/status` (HTML, add `?format=json` for `StatusSnapshot.to_dict()`), `POST /api/clients/clear-dns-cache`, `POST /api/collectors/trigger` (manual on-demand collector run), `POST /api/webhooks/meraki` (validates content-type/size/JSON, delegates to `core/webhook_handler.py`'s `WebhookHandler`)
- `__main__.py` - `main()`: CLI entry point; prints `--help`, surfaces a friendly error when `MERAKI_API_KEY` is missing, then builds `Settings()` and runs `uvicorn.run(create_app(), ...)`
- `__version__.py` - `get_version()`: reads `version` from `pyproject.toml` at runtime (repo-root-relative path), falls back to `importlib.metadata`, then `"0.0.0+dev"`
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

`create_app()` (module-level, in `app.py`) memoizes a single global `FastAPI` instance
(`_app_instance`) — calling it twice returns the same app rather than re-initializing
`ExporterApp` (and re-running `Settings()`/logging/tracing setup) a second time.
</paved_path>
