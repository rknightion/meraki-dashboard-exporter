#!/usr/bin/env python3
"""Generate configuration documentation from Pydantic models.

This script analyzes the Pydantic configuration models and generates
a markdown document listing all configuration options with their descriptions,
types, defaults, and validation constraints.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

try:
    from pydantic_core import PydanticUndefined
except Exception:  # pragma: no cover - fallback for older environments
    PydanticUndefined = object()


def find_repo_root(start_path: Path) -> Path:
    """Find the repository root by walking upwards."""
    for candidate in [start_path, *start_path.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    raise FileNotFoundError("Could not locate repository root (pyproject.toml + src)")


def load_config_models(repo_root: Path) -> Any:
    """Load config_models without importing the package __init__."""
    module_path = repo_root / "src" / "meraki_dashboard_exporter" / "core" / "config_models.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Config models not found at {module_path}")

    spec = importlib.util.spec_from_file_location("config_models", module_path)
    if not spec or not spec.loader:
        raise ImportError("Unable to load config_models module spec")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _format_type(annotation: Any) -> str:
    """Format a type annotation into a readable string."""
    if annotation is type(None):
        return "None"
    if hasattr(annotation, "__forward_arg__"):
        return str(annotation.__forward_arg__)

    origin = get_origin(annotation)
    if origin is None:
        if hasattr(annotation, "__name__"):
            return annotation.__name__
        return str(annotation).replace("typing.", "").replace("NoneType", "None")

    args = get_args(annotation)
    if origin is list:
        return f"list[{_format_type(args[0])}]" if args else "list"
    if origin is set:
        return f"set[{_format_type(args[0])}]" if args else "set"
    if origin is dict:
        if len(args) == 2:
            return f"dict[{_format_type(args[0])}, {_format_type(args[1])}]"
        return "dict"

    # Handle unions (Optional, | None, etc.)
    union_args = " | ".join(_format_type(arg) for arg in args)
    return union_args.replace("NoneType", "None")


def get_field_type_str(field_info: FieldInfo) -> str:
    """Get a human-readable string for a field's type."""
    field_type = field_info.annotation
    return _format_type(field_type)


def format_default(field_info: FieldInfo) -> Any:
    """Format default values for display."""
    if field_info.is_required():
        return "_(required)_"

    default = field_info.default
    if default is PydanticUndefined:
        if field_info.default_factory is not None:
            try:
                default = field_info.default_factory()
            except Exception:
                default = f"{field_info.default_factory.__name__}()"
        else:
            default = None

    if callable(default) and hasattr(default, "__name__"):
        return f"{default.__name__}()"
    if isinstance(default, type):
        return default.__name__
    return default


def extract_constraints(field_info: FieldInfo) -> dict[str, Any]:
    """Extract validation constraints from field metadata."""
    constraints: dict[str, Any] = {}

    for attr in ("ge", "gt", "le", "lt", "min_length", "max_length", "pattern"):
        value = getattr(field_info, attr, None)
        if value is not None:
            constraints[attr] = value

    for metadata in getattr(field_info, "metadata", []) or []:
        for attr in ("ge", "gt", "le", "lt", "min_length", "max_length", "pattern"):
            value = getattr(metadata, attr, None)
            if value is not None:
                constraints.setdefault(attr, value)

    return constraints


def generate_model_docs(model: type[BaseModel], prefix: str = "") -> list[dict[str, Any]]:
    """Generate documentation for a Pydantic model."""
    docs = []

    for field_name, field_info in model.model_fields.items():
        # Build environment variable name
        env_var = f"{prefix}{field_name.upper()}"

        # Get field details
        field_type = get_field_type_str(field_info)
        default = format_default(field_info)

        doc = {
            "env_var": env_var,
            "field": field_name,
            "type": field_type,
            "default": default,
            "description": field_info.description or "",
            "required": field_info.is_required(),
        }

        # Add validation info if present
        constraints = extract_constraints(field_info)
        doc.update(constraints)

        docs.append(doc)

        # Recursively handle nested models
        if (
            field_info.annotation is not None
            and hasattr(field_info.annotation, "__mro__")
            and BaseModel in field_info.annotation.__mro__
        ):
            nested_docs = generate_model_docs(field_info.annotation, prefix=f"{env_var}__")
            docs.extend(nested_docs)

    return docs


def generate_configuration_docs() -> str:
    """Generate complete configuration documentation in mkdocs style."""
    sections = []

    # Header
    sections.append("# Configuration Reference")
    sections.append("")
    sections.append(
        "This document provides a comprehensive reference for all configuration options available in the Meraki Dashboard Exporter."
    )
    sections.append("")

    # Overview section
    sections.append("## Overview")
    sections.append("")
    sections.append("The exporter can be configured using environment variables.")
    sections.append("All configuration is based on Pydantic models with built-in validation.")
    sections.append("")

    # Environment variable format
    sections.append("## Environment Variable Format")
    sections.append("")
    sections.append("Configuration follows a hierarchical structure using environment variables:")
    sections.append("")
    sections.append("- **All settings**: `MERAKI_EXPORTER_{SECTION}__{SETTING}`")
    sections.append("- **Double underscore** (`__`) separates nested configuration levels")
    sections.append("")
    sections.append('!!! example "Environment Variable Examples"')
    sections.append("    ```bash")
    sections.append("    # Meraki API configuration")
    sections.append("    export MERAKI_EXPORTER_MERAKI__API_KEY=your_api_key_here")
    sections.append("    export MERAKI_EXPORTER_MERAKI__ORG_ID=123456")
    sections.append("    ")
    sections.append("    # Logging configuration")
    sections.append("    export MERAKI_EXPORTER_LOGGING__LEVEL=INFO")
    sections.append("    ")
    sections.append("    # API settings")
    sections.append("    export MERAKI_EXPORTER_API__TIMEOUT=30")
    sections.append("    export MERAKI_EXPORTER_API__CONCURRENCY_LIMIT=5")
    sections.append("    ```")
    sections.append("")

    # Nested model sections
    repo_root = find_repo_root(Path(__file__).resolve())
    config_models = load_config_models(repo_root)

    nested_models = [
        (
            "Meraki Settings",
            config_models.MerakiSettings,
            "MERAKI_EXPORTER_MERAKI",
            "Core Meraki API configuration",
        ),
        (
            "Logging Settings",
            config_models.LoggingSettings,
            "MERAKI_EXPORTER_LOGGING",
            "Logging configuration",
        ),
        (
            "API Settings",
            config_models.APISettings,
            "MERAKI_EXPORTER_API",
            "Configuration for Meraki API interactions",
        ),
        (
            "Update Intervals",
            config_models.UpdateIntervals,
            "MERAKI_EXPORTER_UPDATE_INTERVALS",
            "Control how often different types of metrics are collected",
        ),
        (
            "Server Settings",
            config_models.ServerSettings,
            "MERAKI_EXPORTER_SERVER",
            "HTTP server configuration for the metrics endpoint",
        ),
        (
            "Webhook Settings",
            config_models.WebhookSettings,
            "MERAKI_EXPORTER_WEBHOOKS",
            "Webhook receiver configuration",
        ),
        (
            "OpenTelemetry Settings",
            config_models.OTelSettings,
            "MERAKI_EXPORTER_OTEL",
            "OpenTelemetry observability configuration",
        ),
        (
            "Monitoring Settings",
            config_models.MonitoringSettings,
            "MERAKI_EXPORTER_MONITORING",
            "Internal monitoring and alerting configuration",
        ),
        (
            "Collector Settings",
            config_models.CollectorSettings,
            "MERAKI_EXPORTER_COLLECTORS",
            "Enable/disable specific metric collectors",
        ),
        (
            "Client Settings",
            config_models.ClientSettings,
            "MERAKI_EXPORTER_CLIENTS",
            "Client data collection and DNS resolution settings",
        ),
    ]

    section_notes = {
        "Update Intervals": (
            "`MEDIUM` must be greater than or equal to `FAST`, `SLOW` must be greater than or equal "
            "to `MEDIUM`, and `MEDIUM` must be a multiple of `FAST`."
        ),
        "Server Settings": (
            "`PATH_PREFIX` and `ENABLE_HEALTH_CHECK` are currently defined for compatibility, "
            "but the application still exposes `/`, `/health`, `/metrics`, and `/cardinality` "
            "unconditionally."
        ),
        "Webhook Settings": ("Webhooks are received on `POST /api/webhooks/meraki` when enabled."),
    }

    for title, model, prefix, description in nested_models:
        sections.append(f"## {title}")
        sections.append("")
        sections.append(description)
        sections.append("")
        docs = generate_model_docs(model, f"{prefix}__")  # type: ignore[arg-type]

        if docs:
            sections.append("| Environment Variable | Type | Default | Description |")
            sections.append("|---------------------|------|---------|-------------|")
            for doc in docs:
                default = doc["default"]
                if default is None:
                    default = "_(none)_"
                if isinstance(default, list):
                    default = json.dumps(default)
                elif isinstance(default, set):
                    default = json.dumps(sorted(list(default)))

                desc = doc["description"]
                constraint_parts = []
                if "ge" in doc:
                    constraint_parts.append(f"min: {doc['ge']}")
                if "gt" in doc:
                    constraint_parts.append(f"gt: {doc['gt']}")
                if "le" in doc:
                    constraint_parts.append(f"max: {doc['le']}")
                if "lt" in doc:
                    constraint_parts.append(f"lt: {doc['lt']}")
                if "min_length" in doc:
                    constraint_parts.append(f"min_length: {doc['min_length']}")
                if "max_length" in doc:
                    constraint_parts.append(f"max_length: {doc['max_length']}")
                if "pattern" in doc:
                    constraint_parts.append(f"pattern: {doc['pattern']}")

                if constraint_parts:
                    constraints = []
                    constraints.extend(constraint_parts)
                    desc += f" ({', '.join(constraints)})"

                # Escape any pipe characters in the description
                desc = str(desc).replace("|", "\\|")
                sections.append(f"| `{doc['env_var']}` | `{doc['type']}` | `{default}` | {desc} |")
            sections.append("")

        if title in section_notes:
            sections.append(section_notes[title])
            sections.append("")

    sections.append("## Additional Runtime Options")
    sections.append("")
    sections.append(
        "Some runtime knobs are read directly from environment variables and are not part of the"
        " Pydantic settings model:"
    )
    sections.append("")
    sections.append("| Environment Variable | Type | Default | Description |")
    sections.append("|---------------------|------|---------|-------------|")
    sections.append(
        "| `MERAKI_EXPORTER_OTEL__SAMPLING_RATE` | `float` | `0.1` | Trace sampling rate between 0 and 1 |"
    )
    sections.append("")

    return "\n".join(sections)


def main() -> None:
    """Main entry point."""
    repo_root = find_repo_root(Path(__file__).resolve())
    docs_path = repo_root / "docs"
    if not docs_path.exists():
        print("Could not find docs/ directory")
        return

    print("Generating configuration documentation...")

    # Generate markdown
    markdown = generate_configuration_docs()

    # Write to docs/config.md
    output_file = docs_path / "config.md"
    with open(output_file, "w") as f:
        f.write(markdown)
        f.write("\n")  # Ensure file ends with newline

    print(f"Configuration documentation written to {output_file}")


if __name__ == "__main__":
    main()
