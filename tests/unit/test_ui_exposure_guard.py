"""Tests for sensitive-GET exposure hardening (SEC-01 / #558) + /config (#312)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp, ui_guard_decision
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings, ServerSettings

RAW_KEY = "supersecret_api_key_at_least_30_characters_long"


def _settings(*, api_token: str | None = None) -> Settings:
    server = ServerSettings(api_token=SecretStr(api_token)) if api_token else ServerSettings()
    return Settings(
        meraki=MerakiSettings(api_key=SecretStr(RAW_KEY), org_id="123456"),
        server=server,
    )


class TestUiGuardDecision:
    """Pure gating policy (no I/O) - testable without the config flags wired."""

    def test_open_when_no_token_and_ui_enabled(self) -> None:
        """Open when no token and ui enabled."""
        assert (
            ui_guard_decision(
                method="GET",
                path="/status",
                ui_enabled=True,
                api_token=None,
                auth_header="",
            )
            is None
        )

    def test_metrics_never_gated(self) -> None:
        """Metrics never gated."""
        # /metrics must stay scrapeable even with a token set.
        assert (
            ui_guard_decision(
                method="GET",
                path="/metrics",
                ui_enabled=True,
                api_token="tok",
                auth_header="",
            )
            is None
        )

    def test_ui_disabled_suppresses_sensitive_get(self) -> None:
        """Ui disabled suppresses sensitive get."""
        assert ui_guard_decision(
            method="GET",
            path="/clients",
            ui_enabled=False,
            api_token=None,
            auth_header="",
        ) == (404, "Web UI is disabled")

    def test_ui_disabled_suppresses_index(self) -> None:
        """Ui disabled suppresses index."""
        assert ui_guard_decision(
            method="GET",
            path="/",
            ui_enabled=False,
            api_token=None,
            auth_header="",
        ) == (404, "Web UI is disabled")

    def test_token_required_without_auth(self) -> None:
        """Token required without auth."""
        result = ui_guard_decision(
            method="GET",
            path="/clients",
            ui_enabled=True,
            api_token="tok",
            auth_header="",
        )
        assert result == (401, "Invalid or missing API token")

    def test_token_accepts_valid_bearer(self) -> None:
        """Token accepts valid bearer."""
        assert (
            ui_guard_decision(
                method="GET",
                path="/status",
                ui_enabled=True,
                api_token="tok",
                auth_header="Bearer tok",
            )
            is None
        )

    def test_token_rejects_wrong_bearer(self) -> None:
        """Token rejects wrong bearer."""
        result = ui_guard_decision(
            method="GET",
            path="/status",
            ui_enabled=True,
            api_token="tok",
            auth_header="Bearer wrong",
        )
        assert result == (401, "Invalid or missing API token")

    def test_index_not_token_gated(self) -> None:
        """Index not token gated."""
        # The index page is suppressible by ui_enabled but not token-gated.
        assert (
            ui_guard_decision(
                method="GET",
                path="/",
                ui_enabled=True,
                api_token="tok",
                auth_header="",
            )
            is None
        )

    @pytest.mark.parametrize(
        "path",
        [
            "/clients",
            "/status",
            "/config",
            "/cardinality",
            "/cardinality/all-metrics",
            "/api/metrics/cardinality",
        ],
    )
    def test_all_sensitive_paths_token_gated(self, path: str) -> None:
        """All sensitive paths token gated."""
        result = ui_guard_decision(
            method="GET",
            path=path,
            ui_enabled=True,
            api_token="tok",
            auth_header="",
        )
        assert result == (401, "Invalid or missing API token")

    def test_non_get_not_gated(self) -> None:
        """Non get not gated."""
        assert (
            ui_guard_decision(
                method="POST",
                path="/status",
                ui_enabled=True,
                api_token="tok",
                auth_header="",
            )
            is None
        )


class TestTokenGateIntegration:
    """End-to-end middleware behaviour on the real app."""

    def test_sensitive_get_requires_token_when_configured(self) -> None:
        """Sensitive get requires token when configured."""
        exporter = ExporterApp(_settings(api_token="secrettoken"))
        client = TestClient(exporter.create_app(), raise_server_exceptions=True)

        # No token -> 401.
        assert client.get("/status").status_code == 401
        # Correct token -> allowed through.
        ok = client.get("/status", headers={"Authorization": "Bearer secrettoken"})
        assert ok.status_code == 200
        # /metrics stays open with no token.
        assert client.get("/metrics").status_code == 200

    def test_open_by_default(self) -> None:
        """Open by default."""
        exporter = ExporterApp(_settings())
        client = TestClient(exporter.create_app(), raise_server_exceptions=True)
        assert client.get("/status").status_code == 200


class TestConfigEndpoint:
    """/config returns the effective config with secrets redacted (#312)."""

    def test_config_masks_secrets(self) -> None:
        """Config masks secrets."""
        exporter = ExporterApp(_settings())
        client = TestClient(exporter.create_app(), raise_server_exceptions=True)

        resp = client.get("/config")
        assert resp.status_code == 200
        data = resp.json()
        # Secret is masked, and the raw value never appears anywhere in the body.
        assert data["meraki"]["api_key"] == "**********"
        assert RAW_KEY not in resp.text
        # Non-secret resolved config is present.
        assert data["meraki"]["org_id"] == "123456"

    def test_config_token_gated(self) -> None:
        """Config token gated."""
        exporter = ExporterApp(_settings(api_token="secrettoken"))
        client = TestClient(exporter.create_app(), raise_server_exceptions=True)
        assert client.get("/config").status_code == 401
        ok = client.get("/config", headers={"Authorization": "Bearer secrettoken"})
        assert ok.status_code == 200
