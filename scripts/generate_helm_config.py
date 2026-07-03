#!/usr/bin/env python3
"""Generate the Helm chart's config knobs from the Pydantic config schema.

Exposes EVERY ``MERAKI_EXPORTER_*`` tuning knob as a friendly camelCase value in
``charts/.../values.yaml`` (commented at its default, with the field description
as a helm-docs ``# --`` comment) and the matching ``MERAKI_EXPORTER_*`` mapping
in ``templates/configmap.yaml``. Both regions are spliced between BEGIN/END
markers so the rest of each file is preserved.

Friendly names are algorithmic (camelCase of the env-var suffix) with a small
override map for the handful of legacy names that predate the convention, so no
per-knob name table has to be maintained and existing values overrides keep
working. Run via ``make docgen``.
"""

from __future__ import annotations

import sys
import typing
from pathlib import Path
from typing import Any

from pydantic import BaseModel, SecretStr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_config_docs as gcd  # noqa: E402
import generate_env_example as gee  # noqa: E402

BEGIN = "# >>> BEGIN generated config knobs (scripts/generate_helm_config.py) >>>"
END = "# <<< END generated config knobs <<<"

# Env vars wired from other, higher-level chart values (NOT config knobs).
EXCLUDE = {
    "MERAKI_EXPORTER_MERAKI__API_KEY",  # secret (meraki.apiKey / existingSecret)
    "MERAKI_EXPORTER_MERAKI__ORG_ID",  # meraki.organizationId
    "MERAKI_EXPORTER_SERVER__PORT",  # service.port
}

# Legacy friendly names that predate the camelCase convention. Preserved so
# existing users' `config.*` overrides keep working. env-suffix -> friendly.
NAME_OVERRIDES = {
    "LOGGING__LEVEL": "logLevel",
    "MERAKI__API_BASE_URL": "apiBaseUrl",
    "UPDATE_INTERVALS__FAST": "updateIntervalFast",
    "UPDATE_INTERVALS__MEDIUM": "updateIntervalMedium",
    "UPDATE_INTERVALS__SLOW": "updateIntervalSlow",
    "COLLECTORS__COLLECTOR_TIMEOUT": "collectorTimeout",
}


def is_secret(annotation: Any) -> bool:
    """True if the field holds a ``SecretStr`` (bare or in a union, e.g. ``| None``).

    Secret-typed knobs must NOT be templated into a plaintext ConfigMap; operators
    inject them via ``extraEnv`` from a Kubernetes Secret instead.
    """
    if annotation is SecretStr:
        return True
    return any(arg is SecretStr for arg in typing.get_args(annotation))


def friendly_name(env_suffix: str) -> str:
    """Derive a camelCase values key from the env-var suffix (post-prefix)."""
    if env_suffix in NAME_OVERRIDES:
        return NAME_OVERRIDES[env_suffix]
    parts = env_suffix.replace("__", "_").lower().split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def default_str(field_info: Any) -> str:
    """Render a field default as a quoted-string value for a configmap knob."""
    v = gee.format_default(field_info)  # "" for None/secret/empty, else str
    if isinstance(field_info.default, SecretStr):
        return ""
    return v or ""


def collect_knobs() -> list[dict[str, str]]:
    """Walk the Settings model → one dict per settable config knob."""
    repo_root = gcd.find_repo_root(Path(__file__).resolve())
    settings = gee.load_settings_model(repo_root)
    knobs: list[dict[str, str]] = []

    def walk(model: type[BaseModel], prefix: str) -> None:
        for name, info in model.model_fields.items():
            env_var = f"{prefix}{name.upper()}"
            ann = info.annotation
            if gee.is_model(ann):
                walk(ann, f"{env_var}__")
                continue
            if env_var in EXCLUDE:
                continue
            if is_secret(ann):
                # Secrets never go in a ConfigMap; inject via extraEnv from a Secret.
                continue
            suffix = env_var[len(gee.ENV_PREFIX) :]
            desc = " ".join((info.description or "").split()) + gee.constraint_suffix(info)
            knobs.append({
                "env": env_var,
                "key": friendly_name(suffix),
                "default": default_str(info),
                "desc": desc.strip(),
            })

    walk(settings, gee.ENV_PREFIX)
    # Fail loud on a friendly-name collision rather than silently drop a knob.
    seen: dict[str, str] = {}
    for k in knobs:
        if k["key"] in seen:
            raise SystemExit(
                f"friendly-name collision: {k['key']} <- {k['env']} and {seen[k['key']]}"
            )
        seen[k["key"]] = k["env"]
    return knobs


def render_values_block(knobs: list[dict[str, str]]) -> str:
    """The commented, documented knob list for values.yaml (indented 2 spaces)."""
    lines = [f"  {BEGIN}"]
    for k in knobs:
        if k["desc"]:
            lines.append(f"  # -- {k['desc']}")
        lines.append(f'  # {k["key"]}: "{k["default"]}"')
    lines.append(f"  {END}")
    return "\n".join(lines)


def render_configmap_block(knobs: list[dict[str, str]]) -> str:
    """The `with`-guarded env mapping for configmap.yaml (indented 2 spaces)."""
    lines = [f"  {BEGIN}", "  {{- with .Values.config }}"]
    for k in knobs:
        lines.append(f'  {{{{- if hasKey . "{k["key"]}" }}}}')
        lines.append(f"  {k['env']}: {{{{ .{k['key']} | quote }}}}")
        lines.append("  {{- end }}")
    lines.append("  {{- end }}")
    lines.append(f"  {END}")
    return "\n".join(lines)


def splice(path: Path, block: str) -> None:
    """Replace the BEGIN..END region in ``path`` with ``block`` (markers required)."""
    text = path.read_text()
    start = text.find(BEGIN)
    end = text.find(END)
    if start == -1 or end == -1:
        raise SystemExit(f"markers not found in {path} - add {BEGIN} / {END} first")
    # Extend to whole lines (strip leading indent on the BEGIN line, trailing newline on END).
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end == -1 else line_end
    path.write_text(text[:line_start] + block + text[line_end:])


def main() -> None:
    """Regenerate the chart values + configmap knob regions."""
    repo_root = gcd.find_repo_root(Path(__file__).resolve())
    chart = repo_root / "charts" / "meraki-dashboard-exporter"
    knobs = collect_knobs()
    print(f"Generating Helm config knobs ({len(knobs)} settings)...")
    splice(chart / "values.yaml", render_values_block(knobs))
    splice(chart / "templates" / "configmap.yaml", render_configmap_block(knobs))
    print(f"  values.yaml + templates/configmap.yaml updated ({len(knobs)} knobs)")


if __name__ == "__main__":
    main()
