#!/usr/bin/env python3
"""Generate configuration documentation from Pydantic models.

This script analyzes the Pydantic configuration models and generates
a markdown document listing all configuration options with their descriptions,
types, defaults, and validation constraints.
"""

from __future__ import annotations

import json

# Fix imports when running as a script
import sys
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from meraki_dashboard_exporter.core.config_models import (
    APISettings,
    ClientSettings,
    CollectorSettings,
    LoggingSettings,
    MerakiSettings,
    MonitoringSettings,
    OTelSettings,
    ServerSettings,
    SNMPSettings,
    UpdateIntervals,
)


def get_field_type_str(field_info: FieldInfo) -> str:
    """Get a human-readable string for a field's type."""
    field_type = field_info.annotation

    # Handle optional types
    if get_origin(field_type) is type(None):
        return "None"

    # Check if it's Optional (Union with None)
    origin = get_origin(field_type)
    if origin is type:
        args = get_args(field_type)
        if type(None) in args:
            # It's Optional[T]
            non_none_types = [t for t in args if t is not type(None)]
            if len(non_none_types) == 1:
                return f"{non_none_types[0].__name__} | None"

    # Handle literal types
    if hasattr(field_type, "__name__") and field_type is not None:
        return field_type.__name__

    # Handle complex types
    return str(field_type).replace("typing.", "")


def generate_model_docs(model: type[BaseModel], prefix: str = "") -> list[dict[str, Any]]:
    """Generate documentation for a Pydantic model."""
    docs = []

    for field_name, field_info in model.model_fields.items():
        # Build environment variable name
        env_var = f"{prefix}{field_name.upper()}"

        # Get field details
        field_type = get_field_type_str(field_info)
        default = field_info.default
        if callable(default) and hasattr(default, "__name__"):
            default = f"{default.__name__}()"
        elif isinstance(default, type):
            default = f"{default.__name__}"

        doc = {
            "env_var": env_var,
            "field": field_name,
            "type": field_type,
            "default": default,
            "description": field_info.description or "",
            "required": field_info.is_required(),
        }

        # Add validation info if present
        if hasattr(field_info, "ge") and field_info.ge is not None:
            doc["min"] = field_info.ge
        if hasattr(field_info, "le") and field_info.le is not None:
            doc["max"] = field_info.le

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
    nested_models = [
        (
            "Meraki Settings",
            MerakiSettings,
            "MERAKI_EXPORTER_MERAKI",
            "Core Meraki API configuration",
        ),
        (
            "Logging Settings",
            LoggingSettings,
            "MERAKI_EXPORTER_LOGGING",
            "Logging configuration",
        ),
        (
            "API Settings",
            APISettings,
            "MERAKI_EXPORTER_API",
            "Configuration for Meraki API interactions",
        ),
        (
            "Update Intervals",
            UpdateIntervals,
            "MERAKI_EXPORTER_UPDATE_INTERVALS",
            "Control how often different types of metrics are collected",
        ),
        (
            "Server Settings",
            ServerSettings,
            "MERAKI_EXPORTER_SERVER",
            "HTTP server configuration for the metrics endpoint",
        ),
        (
            "OpenTelemetry Settings",
            OTelSettings,
            "MERAKI_EXPORTER_OTEL",
            "OpenTelemetry observability configuration",
        ),
        (
            "Monitoring Settings",
            MonitoringSettings,
            "MERAKI_EXPORTER_MONITORING",
            "Internal monitoring and alerting configuration",
        ),
        (
            "Collector Settings",
            CollectorSettings,
            "MERAKI_EXPORTER_COLLECTORS",
            "Enable/disable specific metric collectors",
        ),
        (
            "Client Settings",
            ClientSettings,
            "MERAKI_EXPORTER_CLIENTS",
            "Client data collection and DNS resolution settings",
        ),
        (
            "SNMP Settings",
            SNMPSettings,
            "MERAKI_EXPORTER_SNMP",
            "SNMP collector configuration for device and cloud controller metrics",
        ),
    ]

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
                default = doc["default"] if doc["default"] is not None else "_(none)_"
                if isinstance(default, list):
                    default = json.dumps(default)
                elif isinstance(default, set):
                    default = json.dumps(sorted(list(default)))

                desc = doc["description"]
                if "min" in doc or "max" in doc:
                    constraints = []
                    if "min" in doc:
                        constraints.append(f"min: {doc['min']}")
                    if "max" in doc:
                        constraints.append(f"max: {doc['max']}")
                    desc += f" ({', '.join(constraints)})"

                # Escape any pipe characters in the description
                desc = str(desc).replace("|", "\\|")
                sections.append(f"| `{doc['env_var']}` | `{doc['type']}` | `{default}` | {desc} |")
            sections.append("")

    return "\n".join(sections)


def main() -> None:
    """Main entry point."""
    # Find project root (where docs/ is)
    current_path = Path.cwd()
    docs_path = current_path / "docs"
    if not docs_path.exists():
        # Try parent directory
        docs_path = current_path.parent / "docs"
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
