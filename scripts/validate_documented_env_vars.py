#!/usr/bin/env python3
"""Validate exact customer-facing environment-variable examples against Settings."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_config_docs as gcd  # noqa: E402
import generate_env_example as gee  # noqa: E402

ENV_VAR_CANDIDATE_RE = re.compile(r"\bMERAKI_EXPORTER_[A-Z0-9_]+\b")
ENV_PREFIX = "MERAKI_EXPORTER_"
EXCLUDED_FILES = {"docs/config.md", "docs/changelog.md"}


def extract_leaf_candidates(text: str) -> set[str]:
    """Extract exact nested environment-variable examples using linear matching."""
    candidates: set[str] = set()
    for variable in ENV_VAR_CANDIDATE_RE.findall(text):
        segments = variable.removeprefix(ENV_PREFIX).split("__")
        if len(segments) < 2 or any(
            not segment or not segment[0].isalpha() for segment in segments
        ):
            continue
        candidates.add(variable)
    return candidates


def settings_leaf_vars(repo_root: Path) -> set[str]:
    """Return exact settable leaf environment variables from the Settings tree."""
    settings = gee.load_settings_model(repo_root)
    leaves: set[str] = set()

    def walk(model: type[BaseModel], prefix: str) -> None:
        for name, field_info in model.model_fields.items():
            env_var = f"{prefix}{name.upper()}"
            if gee.is_model(field_info.annotation):
                walk(field_info.annotation, f"{env_var}__")
            else:
                leaves.add(env_var)

    walk(settings, gee.ENV_PREFIX)
    return leaves


def customer_facing_paths(repo_root: Path) -> list[Path]:
    """List README/docs/chart prose and manifests, excluding generated/scratch files."""
    paths = [repo_root / "README.md"]
    for root in (repo_root / "docs", repo_root / "charts"):
        paths.extend(
            path for path in root.rglob("*") if path.suffix in {".md", ".yaml", ".yml", ".tpl"}
        )
    return sorted(
        path
        for path in paths
        if path.relative_to(repo_root).as_posix() not in EXCLUDED_FILES
        and "superpowers" not in path.relative_to(repo_root).parts
    )


def validate_documented_env_vars(paths: list[Path], valid_vars: set[str]) -> None:
    """Fail when an exact documented leaf variable is not present in Settings."""
    unknown: list[str] = []
    for path in paths:
        for variable in extract_leaf_candidates(path.read_text(encoding="utf-8")):
            if variable not in valid_vars:
                unknown.append(f"{path}: {variable}")
    if unknown:
        raise RuntimeError(
            "Unknown documented environment variable(s): " + "; ".join(sorted(set(unknown)))
        )


def main() -> None:
    """Validate customer-facing environment-variable examples."""
    repo_root = gcd.find_repo_root(Path(__file__).resolve())
    validate_documented_env_vars(customer_facing_paths(repo_root), settings_leaf_vars(repo_root))


if __name__ == "__main__":
    main()
