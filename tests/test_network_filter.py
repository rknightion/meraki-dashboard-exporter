"""Tests for the NetworkFilter resolver."""

from __future__ import annotations

import pytest

from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
from meraki_dashboard_exporter.core.network_filter import NetworkFilter

PROD_LON = {"id": "L_1", "name": "prod-london", "tags": ["production", "eu"]}
PROD_NYC = {"id": "L_2", "name": "prod-newyork", "tags": ["production", "us"]}
STAGING = {"id": "L_3", "name": "staging-london", "tags": ["staging"]}
LAB = {"id": "L_4", "name": "lab-experiments", "tags": ["lab", "internal"]}
UNTAGGED = {"id": "L_5", "name": "office-wifi", "tags": []}
ALL_NETWORKS = [PROD_LON, PROD_NYC, STAGING, LAB, UNTAGGED]


def _ids(networks: list[dict]) -> list[str]:
    return [n["id"] for n in networks]


def test_inactive_filter_returns_all() -> None:
    """An inactive filter passes every network through."""
    f = NetworkFilter(NetworkFilterSettings())
    assert f.is_active is False
    assert _ids(f.apply(ALL_NETWORKS)) == _ids(ALL_NETWORKS)


def test_include_by_name_glob() -> None:
    """Name globs select networks whose name matches any pattern."""
    f = NetworkFilter(NetworkFilterSettings(include_names=["prod-*"]))
    assert _ids(f.apply(ALL_NETWORKS)) == ["L_1", "L_2"]


def test_include_by_id() -> None:
    """Exact-ID includes select only the listed networks."""
    f = NetworkFilter(NetworkFilterSettings(include_ids=["L_3", "L_5"]))
    assert _ids(f.apply(ALL_NETWORKS)) == ["L_3", "L_5"]


def test_include_by_tag() -> None:
    """Tag includes select networks carrying any of the listed tags."""
    f = NetworkFilter(NetworkFilterSettings(include_tags=["production"]))
    assert _ids(f.apply(ALL_NETWORKS)) == ["L_1", "L_2"]


def test_include_is_or_across_dimensions() -> None:
    """Includes are OR'd across name/id/tag dimensions."""
    f = NetworkFilter(NetworkFilterSettings(include_names=["lab-*"], include_tags=["staging"]))
    assert _ids(f.apply(ALL_NETWORKS)) == ["L_3", "L_4"]


def test_exclude_after_include() -> None:
    """Excludes are applied after includes."""
    f = NetworkFilter(NetworkFilterSettings(include_names=["prod-*"], exclude_tags=["us"]))
    assert _ids(f.apply(ALL_NETWORKS)) == ["L_1"]


def test_exclude_beats_include_when_overlap() -> None:
    """If a network matches both include and exclude, it is dropped."""
    f = NetworkFilter(NetworkFilterSettings(include_ids=["L_1", "L_2"], exclude_ids=["L_1"]))
    assert _ids(f.apply(ALL_NETWORKS)) == ["L_2"]


def test_exclude_only_default_includes_everything_else() -> None:
    """With no includes, all networks are considered then excludes filter them."""
    f = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
    assert _ids(f.apply(ALL_NETWORKS)) == ["L_1", "L_2", "L_3", "L_5"]


def test_name_match_is_case_sensitive() -> None:
    """Name globs are case-sensitive."""
    f = NetworkFilter(NetworkFilterSettings(include_names=["PROD-*"]))
    assert f.apply(ALL_NETWORKS) == []


def test_tag_match_against_multi_tag_network() -> None:
    """A multi-tag network matches if any tag overlaps the include set."""
    f = NetworkFilter(NetworkFilterSettings(include_tags=["eu"]))
    assert _ids(f.apply(ALL_NETWORKS)) == ["L_1"]


def test_resolved_ids_returns_set_of_strings() -> None:
    """resolved_ids returns the IDs of networks that passed the filter."""
    f = NetworkFilter(NetworkFilterSettings(include_names=["prod-*"]))
    assert f.resolved_ids(ALL_NETWORKS) == {"L_1", "L_2"}


def test_network_without_tags_field_is_handled() -> None:
    """A network missing the tags key does not raise."""
    f = NetworkFilter(NetworkFilterSettings(include_tags=["any"]))
    odd = [{"id": "L_X", "name": "no-tags-field"}]
    assert f.apply(odd) == []


def test_unmatched_include_id_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """An include_id that matches nothing produces a warning log.

    structlog routes through its own pipeline, so caplog does not capture
    these messages reliably. Monkeypatching the module logger captures the
    structured kwargs directly.
    """
    from meraki_dashboard_exporter.core import network_filter as nf_mod

    captured: list[dict] = []

    def _fake_warning(message: str, **kwargs: object) -> None:
        captured.append({"message": message, **kwargs})

    monkeypatch.setattr(nf_mod.logger, "warning", _fake_warning)

    f = NetworkFilter(NetworkFilterSettings(include_ids=["L_NONEXISTENT"]))
    result = f.apply(ALL_NETWORKS)
    assert result == []
    assert any(entry.get("missing_id") == "L_NONEXISTENT" for entry in captured)


def test_inactive_apply_returns_shallow_copy() -> None:
    """apply on an inactive filter returns a new list (not the same object)."""
    f = NetworkFilter(NetworkFilterSettings())
    result = f.apply(ALL_NETWORKS)
    assert result == ALL_NETWORKS
    assert result is not ALL_NETWORKS
