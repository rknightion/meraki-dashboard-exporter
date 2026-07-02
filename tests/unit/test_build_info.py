"""Tests for the static exporter build-info metric (MET-10, issue #537)."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY, CollectorRegistry
from pydantic import SecretStr

from meraki_dashboard_exporter.__version__ import get_commit, get_version
from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.build_info import register_build_info
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings


def test_register_build_info_emits_value_1_with_version_and_commit() -> None:
    """build_info is a constant gauge of 1 labelled with the real build version + commit."""
    registry = CollectorRegistry()
    register_build_info(registry)

    value = registry.get_sample_value(
        "meraki_exporter_build_info",
        {"version": get_version(), "commit": get_commit()},
    )
    assert value == 1


def test_build_info_commit_dev_fallback_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dev/local builds without the GIT_COMMIT build-arg report commit 'unknown' (DEP-06)."""
    monkeypatch.delenv("MERAKI_EXPORTER_COMMIT", raising=False)

    registry = CollectorRegistry()
    register_build_info(registry)

    value = registry.get_sample_value(
        "meraki_exporter_build_info",
        {"version": get_version(), "commit": "unknown"},
    )
    assert value == 1


def test_get_commit_prefers_baked_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The commit is sourced from the MERAKI_EXPORTER_COMMIT build-time env var."""
    monkeypatch.setenv("MERAKI_EXPORTER_COMMIT", "deadbeefcafe")
    assert get_commit() == "deadbeefcafe"


def test_get_commit_dev_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no baked commit env var, fall back to the 'unknown' sentinel (DEP-06)."""
    monkeypatch.delenv("MERAKI_EXPORTER_COMMIT", raising=False)
    assert get_commit() == "unknown"


def test_exporter_app_registers_build_info_on_default_registry() -> None:
    """Constructing the app wires build_info onto the global Prometheus registry."""
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )
    ExporterApp(settings)

    value = REGISTRY.get_sample_value(
        "meraki_exporter_build_info",
        {"version": get_version(), "commit": get_commit()},
    )
    assert value == 1
