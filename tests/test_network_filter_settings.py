"""Tests for NetworkFilterSettings env parsing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings


def test_empty_config_has_empty_lists() -> None:
    """All list fields default to empty lists when nothing is configured."""
    s = NetworkFilterSettings()
    assert s.include_names == []
    assert s.include_ids == []
    assert s.include_tags == []
    assert s.exclude_names == []
    assert s.exclude_ids == []
    assert s.exclude_tags == []


def test_csv_string_parses_into_list() -> None:
    """A comma-separated env-var string is split into a list."""
    s = NetworkFilterSettings(include_names="prod-*, staging-*")  # type: ignore[arg-type]
    assert s.include_names == ["prod-*", "staging-*"]


def test_json_array_string_parses_into_list() -> None:
    """A JSON-array string (matching ``histogram_buckets`` style) parses into a list."""
    s = NetworkFilterSettings(include_names='["prod-*", "staging-*"]')  # type: ignore[arg-type]
    assert s.include_names == ["prod-*", "staging-*"]


def test_empty_string_is_empty_list() -> None:
    """An empty or whitespace-only string is treated as an empty list."""
    s = NetworkFilterSettings(include_names="")  # type: ignore[arg-type]
    assert s.include_names == []


def test_whitespace_is_stripped() -> None:
    """Whitespace-only items are dropped and surrounding whitespace is trimmed."""
    s = NetworkFilterSettings(include_ids="  L_1  ,L_2,  ,L_3  ")  # type: ignore[arg-type]
    assert s.include_ids == ["L_1", "L_2", "L_3"]


def test_invalid_input_type_raises() -> None:
    """A non-list / non-string value raises a ValidationError.

    ``fnmatch.translate`` is intentionally liberal and does not raise on most
    string patterns, so this test instead exercises the type-rejection branch
    of ``_split_csv``.
    """
    with pytest.raises(ValidationError):
        NetworkFilterSettings(include_names={"not": "a list"})  # type: ignore[arg-type]


def test_is_active_property() -> None:
    """``is_active`` reflects whether any include or exclude rule is configured."""
    assert NetworkFilterSettings().is_active is False
    assert NetworkFilterSettings(include_names=["x"]).is_active is True
    assert NetworkFilterSettings(exclude_tags=["lab"]).is_active is True
