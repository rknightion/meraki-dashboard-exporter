#!/usr/bin/env python3
"""Generate configuration documentation from Pydantic models.

This script analyzes the Pydantic configuration models and generates
a markdown document listing all configuration options with their descriptions,
types, defaults, and validation constraints.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from ..core.config import Settings
from ..core.config_models import (
    PROFILES,
    APISettings,
    ClientSettings,
    CollectorSettings,
    MonitoringSettings,
    OTelSettings,
    ServerSettings,
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
    sections.append(
        "The exporter can be configured using environment variables or configuration files. "
    )
    sections.append("All configuration is based on Pydantic models with built-in validation.")
    sections.append("")

    # Environment variable format
    sections.append("## Environment Variable Format")
    sections.append("")
    sections.append("Configuration follows a hierarchical structure using environment variables:")
    sections.append("")
    sections.append("- **Main settings**: `MERAKI_EXPORTER_{SETTING}`")
    sections.append("- **Nested settings**: `MERAKI_EXPORTER_{SECTION}__{SETTING}`")
    sections.append("- **Special case**: `MERAKI_API_KEY` (no prefix required)")
    sections.append("")
    sections.append('!!! example "Environment Variable Examples"')
    sections.append("    ```bash")
    sections.append("    # Main setting")
    sections.append("    export MERAKI_EXPORTER_LOG_LEVEL=INFO")
    sections.append("    ")
    sections.append("    # Nested setting")
    sections.append("    export MERAKI_EXPORTER_API__TIMEOUT=30")
    sections.append("    ")
    sections.append("    # API key (special case)")
    sections.append("    export MERAKI_API_KEY=your_api_key_here")
    sections.append("    ```")
    sections.append("")

    # Generate docs for main settings
    main_docs = []
    for field_name, field_info in Settings.model_fields.items():
        if field_name in [
            "api",
            "update_intervals",
            "server",
            "otel",
            "monitoring",
            "collectors",
            "clients",
        ]:
            continue  # Handle these separately

        env_var = f"MERAKI_EXPORTER_{field_name.upper()}"
        if field_name == "api_key":
            env_var = "MERAKI_API_KEY"

        main_docs.append({
            "env_var": env_var,
            "field": field_name,
            "type": get_field_type_str(field_info),
            "default": field_info.default,
            "description": field_info.description or "",
            "required": field_info.is_required(),
        })

    # Main settings section
    sections.append("## Main Settings")
    sections.append("")
    sections.append("These are the primary configuration options for the exporter:")
    sections.append("")
    sections.append("| Environment Variable | Type | Default | Required | Description |")
    sections.append("|---------------------|------|---------|----------|-------------|")
    for doc in main_docs:
        required = "✅ Yes" if doc["required"] else "❌ No"
        default = doc["default"] if doc["default"] is not None else "_(none)_"
        # Escape any pipe characters in the description
        description = str(doc["description"]).replace("|", "\\|")
        sections.append(
            f"| `{doc['env_var']}` | `{doc['type']}` | `{default}` | {required} | {description} |"
        )
    sections.append("")

    # Nested model sections
    nested_models = [
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

    # Configuration profiles
    sections.append("## Configuration Profiles")
    sections.append("")
    sections.append(
        "Pre-defined configuration profiles provide optimized settings for different deployment scenarios. "
        "Activate a profile using `MERAKI_EXPORTER_PROFILE`."
    )
    sections.append("")

    for name, profile in PROFILES.items():
        sections.append(f"### {name.title()}")
        sections.append("")
        sections.append(f"**Description:** {profile.description}")
        sections.append("")
        sections.append("**Usage:**")
        sections.append("```bash")
        sections.append(f"export MERAKI_EXPORTER_PROFILE={name}")
        sections.append("```")
        sections.append("")
        sections.append("**Key Settings:**")
        sections.append("")
        sections.append(
            f"- **API Concurrency:** {profile.api.concurrency_limit} concurrent requests"
        )
        sections.append(f"- **Batch Size:** {profile.api.batch_size} items per batch")
        sections.append(f"- **API Timeout:** {profile.api.timeout} seconds")
        sections.append(
            f"- **Update Intervals:** {profile.update_intervals.fast}s / {profile.update_intervals.medium}s / {profile.update_intervals.slow}s"
        )
        sections.append(f"- **Max Failures:** {profile.monitoring.max_consecutive_failures}")
        sections.append(f"- **Collector Timeout:** {profile.collectors.collector_timeout} seconds")
        sections.append(
            f"- **Client Collection:** {'Enabled' if profile.clients.enabled else 'Disabled'}"
        )
        sections.append("")

    # Examples section
    sections.append("## Configuration Examples")
    sections.append("")

    sections.append("### Basic Setup")
    sections.append("")
    sections.append("Minimal configuration for getting started:")
    sections.append("")
    sections.append("```bash")
    sections.append("export MERAKI_API_KEY=your_api_key_here")
    sections.append("export MERAKI_EXPORTER_LOG_LEVEL=INFO")
    sections.append("```")
    sections.append("")

    sections.append("### Production Deployment")
    sections.append("")
    sections.append("Production-ready configuration with optimized settings:")
    sections.append("")
    sections.append("```bash")
    sections.append("export MERAKI_API_KEY=your_api_key_here")
    sections.append("export MERAKI_EXPORTER_PROFILE=production")
    sections.append("export MERAKI_EXPORTER_ORG_ID=123456")
    sections.append("export MERAKI_EXPORTER_API__CONCURRENCY_LIMIT=10")
    sections.append("export MERAKI_EXPORTER_API__TIMEOUT=45")
    sections.append("export MERAKI_EXPORTER_OTEL__ENABLED=true")
    sections.append("export MERAKI_EXPORTER_OTEL__ENDPOINT=http://otel-collector:4317")
    sections.append("```")
    sections.append("")

    sections.append("### High Volume Environment")
    sections.append("")
    sections.append("Configuration for large organizations with many devices:")
    sections.append("")
    sections.append("```bash")
    sections.append("export MERAKI_API_KEY=your_api_key_here")
    sections.append("export MERAKI_EXPORTER_PROFILE=high_volume")
    sections.append("export MERAKI_EXPORTER_UPDATE_INTERVALS__FAST=120")
    sections.append("export MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM=600")
    sections.append("export MERAKI_EXPORTER_UPDATE_INTERVALS__SLOW=1800")
    sections.append("export MERAKI_EXPORTER_API__CONCURRENCY_LIMIT=15")
    sections.append("export MERAKI_EXPORTER_API__BATCH_SIZE=20")
    sections.append("export MERAKI_EXPORTER_MONITORING__MAX_CONSECUTIVE_FAILURES=20")
    sections.append("```")
    sections.append("")

    sections.append("### Development Environment")
    sections.append("")
    sections.append("Configuration for development and testing:")
    sections.append("")
    sections.append("```bash")
    sections.append("export MERAKI_API_KEY=your_api_key_here")
    sections.append("export MERAKI_EXPORTER_PROFILE=development")
    sections.append("export MERAKI_EXPORTER_LOG_LEVEL=DEBUG")
    sections.append("export MERAKI_EXPORTER_SERVER__PORT=9099")
    sections.append("```")
    sections.append("")

    # Best practices section
    sections.append("## Best Practices")
    sections.append("")
    sections.append('!!! tip "Configuration Recommendations"')
    sections.append("    - **Use profiles** for consistent deployments across environments")
    sections.append(
        "    - **Set organization ID** (`MERAKI_EXPORTER_ORG_ID`) to limit scope and improve performance"
    )
    sections.append("    - **Adjust intervals** based on your monitoring needs and API rate limits")
    sections.append("    - **Enable OpenTelemetry** in production for better observability")
    sections.append("    - **Monitor API usage** to stay within Meraki's rate limits")
    sections.append("")
    sections.append('!!! warning "Important Notes"')
    sections.append("    - The `MERAKI_API_KEY` is required and must be kept secure")
    sections.append("    - Some metrics require specific Meraki license types")
    sections.append("    - Network-specific collectors may not work with all device types")
    sections.append("    - Rate limiting is automatically handled but can be tuned")
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

    print(f"Configuration documentation written to {output_file}")


if __name__ == "__main__":
    main()
