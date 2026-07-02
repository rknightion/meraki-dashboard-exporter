"""Tests for get_version()'s baked-in env fallback (F-118)."""

from __future__ import annotations

import importlib.metadata as ilm

import pytest

from meraki_dashboard_exporter import __version__ as ver_mod


def _force_local_sources_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the pyproject.toml and importlib.metadata lookups both miss.

    Mirrors the runtime container image, where pyproject.toml is not present
    and the package is not pip-installed (``uv sync --no-install-project``).
    """
    # pyproject.toml lookup misses
    monkeypatch.setattr(ver_mod.Path, "exists", lambda self: False)

    # importlib.metadata.version raises PackageNotFoundError
    def _raise(name: str) -> str:
        raise ilm.PackageNotFoundError(name)

    monkeypatch.setattr(ilm, "version", _raise)


def test_get_version_uses_baked_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When local sources miss, the baked env var supplies the version (F-118)."""
    _force_local_sources_unavailable(monkeypatch)
    monkeypatch.setenv("MERAKI_EXPORTER_VERSION", "9.9.9-baked")

    assert ver_mod.get_version() == "9.9.9-baked"


def test_get_version_dev_fallback_when_nothing_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no source and no baked env var, fall back to the dev sentinel."""
    _force_local_sources_unavailable(monkeypatch)
    monkeypatch.delenv("MERAKI_EXPORTER_VERSION", raising=False)

    assert ver_mod.get_version() == "0.0.0+dev"


def test_get_version_prefers_local_source_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A working local source (pyproject/metadata) wins over the baked env var."""
    # Env var set, but the real pyproject.toml is readable in the repo checkout,
    # so get_version() must return the real version, not the baked sentinel.
    monkeypatch.setenv("MERAKI_EXPORTER_VERSION", "9.9.9-baked")

    result = ver_mod.get_version()

    assert result != "9.9.9-baked"
    assert result != "0.0.0+dev"
