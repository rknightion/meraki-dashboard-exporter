#!/usr/bin/env python3
"""Generate configuration documentation from Pydantic models."""

from __future__ import annotations

import json
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from ..core.config import Settings
from ..core.config_models import (
    PROFILES,
    APISettings,
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
    if hasattr(field_type, "__name__"):
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
        if hasattr(default, "__call__") and hasattr(default, "__name__"):
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
            hasattr(field_info.annotation, "__mro__") and
            BaseModel in field_info.annotation.__mro__
        ):
            nested_docs = generate_model_docs(
                field_info.annotation,
                prefix=f"{env_var}__"
            )
            docs.extend(nested_docs)
    
    return docs


def generate_configuration_docs() -> str:
    """Generate complete configuration documentation."""
    sections = []
    
    # Header
    sections.append("# Configuration Reference\n")
    sections.append("This document lists all available configuration options for the Meraki Dashboard Exporter.\n")
    
    # Environment variable format
    sections.append("## Environment Variable Format\n")
    sections.append("- Most variables use the prefix `MERAKI_EXPORTER_`")
    sections.append("- Nested settings use double underscore: `MERAKI_EXPORTER_API__TIMEOUT`")
    sections.append("- Special case: `MERAKI_API_KEY` (no prefix required)\n")
    
    # Generate docs for main settings
    main_docs = []
    for field_name, field_info in Settings.model_fields.items():
        if field_name in ["api", "update_intervals", "server", "otel", "monitoring", "collectors"]:
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
    sections.append("## Main Settings\n")
    sections.append("| Environment Variable | Type | Default | Required | Description |")
    sections.append("|---------------------|------|---------|----------|-------------|")
    for doc in main_docs:
        required = "Yes" if doc["required"] else "No"
        default = doc["default"] if doc["default"] is not None else ""
        sections.append(f"| `{doc['env_var']}` | {doc['type']} | {default} | {required} | {doc['description']} |")
    sections.append("")
    
    # Nested model sections
    nested_models = [
        ("API Settings", APISettings, "MERAKI_EXPORTER_API"),
        ("Update Intervals", UpdateIntervals, "MERAKI_EXPORTER_UPDATE_INTERVALS"),
        ("Server Settings", ServerSettings, "MERAKI_EXPORTER_SERVER"),
        ("OpenTelemetry Settings", OTelSettings, "MERAKI_EXPORTER_OTEL"),
        ("Monitoring Settings", MonitoringSettings, "MERAKI_EXPORTER_MONITORING"),
        ("Collector Settings", CollectorSettings, "MERAKI_EXPORTER_COLLECTORS"),
    ]
    
    for title, model, prefix in nested_models:
        sections.append(f"## {title}\n")
        docs = generate_model_docs(model, f"{prefix}__")
        
        sections.append("| Environment Variable | Type | Default | Description |")
        sections.append("|---------------------|------|---------|-------------|")
        for doc in docs:
            default = doc["default"] if doc["default"] is not None else ""
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
            
            sections.append(f"| `{doc['env_var']}` | {doc['type']} | {default} | {desc} |")
        sections.append("")
    
    # Configuration profiles
    sections.append("## Configuration Profiles\n")
    sections.append("Pre-defined configuration profiles can be activated using `MERAKI_EXPORTER_PROFILE`.\n")
    sections.append("Available profiles:\n")
    
    for name, profile in PROFILES.items():
        sections.append(f"### {name}\n")
        sections.append(f"{profile.description}\n")
        sections.append("```bash")
        sections.append(f"export MERAKI_EXPORTER_PROFILE={name}")
        sections.append("```\n")
        sections.append("Key settings:")
        sections.append(f"- API concurrency: {profile.api.concurrency_limit}")
        sections.append(f"- Batch size: {profile.api.batch_size}")
        sections.append(f"- Update intervals: {profile.update_intervals.fast}s / {profile.update_intervals.medium}s / {profile.update_intervals.slow}s")
        sections.append("")
    
    # Examples
    sections.append("## Configuration Examples\n")
    sections.append("### Basic Configuration\n")
    sections.append("```bash")
    sections.append("export MERAKI_API_KEY=your_api_key_here")
    sections.append("export MERAKI_EXPORTER_LOG_LEVEL=INFO")
    sections.append("```\n")
    
    sections.append("### Production with Custom API Settings\n")
    sections.append("```bash")
    sections.append("export MERAKI_API_KEY=your_api_key_here")
    sections.append("export MERAKI_EXPORTER_PROFILE=production")
    sections.append("export MERAKI_EXPORTER_API__CONCURRENCY_LIMIT=10")
    sections.append("export MERAKI_EXPORTER_API__TIMEOUT=45")
    sections.append("```\n")
    
    sections.append("### High Volume Deployment\n")
    sections.append("```bash")
    sections.append("export MERAKI_API_KEY=your_api_key_here")
    sections.append("export MERAKI_EXPORTER_PROFILE=high_volume")
    sections.append("export MERAKI_EXPORTER_UPDATE_INTERVALS__FAST=120")
    sections.append("export MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM=600")
    sections.append("export MERAKI_EXPORTER_MONITORING__MAX_CONSECUTIVE_FAILURES=20")
    sections.append("```\n")
    
    return "\n".join(sections)


def main() -> None:
    """Generate and print configuration documentation."""
    docs = generate_configuration_docs()
    print(docs)


if __name__ == "__main__":
    main()