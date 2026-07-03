#!/usr/bin/env python3
"""Generate ``.env.example`` from the Pydantic config models.

Single source of truth: this introspects the SAME ``Settings`` model that
``generate_config_docs.py`` documents, so ``.env.example`` can never drift from
the config schema. Every settable environment variable is emitted, grouped by
its top-level section, commented out at its default (required fields are emitted
uncommented with an empty value), with the field description as a comment.

Run via ``make docgen`` (wired into ``scripts/generate-docs.sh``).
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

from pydantic import BaseModel, SecretStr
from pydantic.fields import FieldInfo

try:
    from pydantic_core import PydanticUndefined
except Exception:  # pragma: no cover
    PydanticUndefined = object()

# Reuse the battle-tested repo-root finder + constraint extractor from the
# sibling generator so the two stay consistent.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_config_docs as gcd  # noqa: E402

ENV_PREFIX = "MERAKI_EXPORTER_"

# Human-friendly section headers keyed by the top-level Settings field name.
# Any field not listed falls back to an upper-cased/underscored title, so a new
# settings group still renders correctly without touching this map.
SECTION_TITLES: dict[str, str] = {
    "meraki": "MERAKI API (required key + org/region)",
    "logging": "LOGGING",
    "api": "MERAKI API TUNING (retries, batching, concurrency, rate limiting)",
    "server": "HTTP SERVER",
    "webhooks": "WEBHOOK RECEIVER",
    "otel": "OPENTELEMETRY (traces + data logs + OTLP metrics bridge)",
    "monitoring": "MONITORING & HEALTH",
    "collectors": "COLLECTOR TOGGLES & BEHAVIOUR",
    "cardinality": "CARDINALITY GUARD",
    "clients": "CLIENT / PER-USER COLLECTION",
    "network_filter": "NETWORK FILTER (restrict scraping to a subset of networks)",
    "scheduler": "ADAPTIVE SCHEDULER",
}


def load_settings_model(repo_root: Path) -> type[BaseModel]:
    """Load the top-level ``Settings`` model without importing the package init."""
    # Register lightweight stub parent packages (same technique as
    # generate_config_docs.load_config_models) so config.py's relative imports
    # resolve without executing the heavy package __init__.
    src_root = repo_root / "src"
    for name, path in (
        ("meraki_dashboard_exporter", src_root / "meraki_dashboard_exporter"),
        ("meraki_dashboard_exporter.core", src_root / "meraki_dashboard_exporter" / "core"),
    ):
        if name not in sys.modules:
            stub = importlib.util.module_from_spec(
                importlib.machinery.ModuleSpec(name, None, is_package=True)
            )
            stub.__path__ = [str(path)]  # type: ignore[attr-defined]
            sys.modules[name] = stub

    module_path = src_root / "meraki_dashboard_exporter" / "core" / "config.py"
    spec = importlib.util.spec_from_file_location(
        "meraki_dashboard_exporter.core.config", module_path
    )
    if not spec or not spec.loader:
        raise ImportError(f"Cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.Settings  # type: ignore[no-any-return]


def is_model(annotation: Any) -> bool:
    """True if the annotation is a nested pydantic model."""
    return (
        isinstance(annotation, type)
        and hasattr(annotation, "__mro__")
        and BaseModel in annotation.__mro__
    )


def format_default(field_info: FieldInfo) -> str | None:
    """Render a field default as an env-var value, or None if there is none.

    Returns None when the field is required (no default) so the caller emits it
    uncommented with an empty value.
    """
    default = field_info.default
    if default is PydanticUndefined:
        if field_info.default_factory is not None:
            try:
                default = field_info.default_factory()  # type: ignore[call-arg]
            except Exception:
                return ""
        else:
            return None  # genuinely required
    if default is None:
        return ""
    if isinstance(default, SecretStr):
        return ""
    if isinstance(default, bool):
        return "true" if default else "false"
    if isinstance(default, (set, frozenset)):
        # Sort for deterministic output (set iteration order is hash-randomised);
        # render as a JSON array, which is how pydantic parses a set field from env.
        return "" if not default else json.dumps(sorted(default, key=str))
    if isinstance(default, (list, dict)):
        return "" if not default else json.dumps(default)
    return str(default)


def wrap_comment(text: str, width: int = 76) -> list[str]:
    """Wrap ``text`` into ``# ``-prefixed comment lines."""
    text = " ".join(str(text).split())
    if not text:
        return []
    return [f"# {line}" for line in textwrap.wrap(text, width=width)]


def constraint_suffix(field_info: FieldInfo) -> str:
    """Return a ``(min: .., max: ..)``-style suffix from field constraints."""
    c = gcd.extract_constraints(field_info)
    parts: list[str] = []
    for key, label in (("ge", "min"), ("gt", "min"), ("le", "max"), ("lt", "max")):
        if key in c:
            parts.append(f"{label}: {c[key]}")
    return f" ({', '.join(parts)})" if parts else ""


def emit_model(model: type[BaseModel], prefix: str) -> list[str]:
    """Emit env-var lines for every leaf field of ``model`` (recursing nested)."""
    lines: list[str] = []
    for field_name, field_info in model.model_fields.items():
        env_var = f"{prefix}{field_name.upper()}"
        ann = field_info.annotation
        if is_model(ann):
            lines.extend(emit_model(ann, f"{env_var}__"))
            continue
        desc = (field_info.description or "").strip()
        lines.extend(wrap_comment(desc + constraint_suffix(field_info)))
        value = format_default(field_info)
        if value is None:
            lines.append("# REQUIRED - set this.")
            lines.append(f"{env_var}=")
        else:
            lines.append(f"# {env_var}={value}")
        lines.append("")
    return lines


def generate() -> str:
    """Render the complete ``.env.example`` body."""
    repo_root = gcd.find_repo_root(Path(__file__).resolve())
    settings = load_settings_model(repo_root)

    out: list[str] = [
        "# Meraki Dashboard Exporter - environment variable reference",
        "#",
        "# GENERATED by scripts/generate_env_example.py from the Pydantic config",
        "# models (the same source as docs/config.md). DO NOT EDIT BY HAND - run",
        "# `make docgen` to regenerate. Every settable variable is listed here,",
        "# commented at its default; uncomment and change what you need. Required",
        "# variables are shown uncommented with an empty value.",
        "#",
        "# Nested config uses `__` (double underscore): MERAKI_EXPORTER_<SECTION>__<SETTING>.",
        "",
    ]
    for field_name, field_info in settings.model_fields.items():
        ann = field_info.annotation
        if not is_model(ann):
            continue
        title = SECTION_TITLES.get(field_name, field_name.upper().replace("_", " "))
        out.append("# " + "=" * 74)
        out.append(f"# {title}")
        # Use the nested model's docstring first line as a section intro if present.
        doc = (ann.__doc__ or "").strip().split("\n")[0].strip()
        if doc and doc.lower() not in title.lower():
            out.extend(wrap_comment(doc))
        out.append("# " + "=" * 74)
        out.append("")
        out.extend(emit_model(ann, f"{ENV_PREFIX}{field_name.upper()}__"))
    # collapse any trailing blank lines to a single newline
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


def main() -> None:
    """Write ``.env.example`` at the repo root."""
    repo_root = gcd.find_repo_root(Path(__file__).resolve())
    output = repo_root / ".env.example"
    print("Generating .env.example from config models...")
    output.write_text(generate())
    print(f".env.example written to {output}")


if __name__ == "__main__":
    main()
