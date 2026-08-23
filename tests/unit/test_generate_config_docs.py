"""Focused regression coverage for generated configuration table cells."""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import generate_config_docs as gcd_config  # noqa: E402


def test_union_type_cell_escapes_table_delimiters_without_changing_type() -> None:
    """A Literal union remains one Markdown cell with its original type text."""
    repo_root = gcd_config.find_repo_root(SCRIPTS_DIR)
    config_models = gcd_config.load_config_models(repo_root)
    profile_type = gcd_config.get_field_type_str(
        config_models.CollectorSettings.model_fields["profile"]
    )
    assert profile_type == "availability | standard | full | None"

    markdown = gcd_config.generate_configuration_docs()
    profile_row = next(
        line for line in markdown.splitlines() if "MERAKI_EXPORTER_COLLECTORS__PROFILE" in line
    )

    escaped_type = r"availability \| standard \| full \| None"
    assert f"`{escaped_type}`" in profile_row
    assert escaped_type.replace(r"\|", "|") == "availability | standard | full | None"
    assert len(re.findall(r"(?<!\\)\|", profile_row)) == 5
