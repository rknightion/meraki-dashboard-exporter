"""Regression tests for fail-closed control endpoints and their UI controls (#695)."""

from __future__ import annotations

from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from meraki_dashboard_exporter.api.client import AsyncMerakiClient
from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings

CONTROL_DISABLED_TOOLTIP = "Configure server.api_token to enable manual controls."


class _ControlButtonParser(HTMLParser):
    """Collect attributes from the two state-changing UI controls."""

    def __init__(self) -> None:
        super().__init__()
        self.buttons: dict[str, dict[str, str | None]] = {}

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "button":
            return
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        for control_class in ("collector-trigger", "clear-cache-btn"):
            if control_class in classes:
                self.buttons[control_class] = attributes


def _control_attributes(html: str, control_class: str) -> dict[str, str | None]:
    parser = _ControlButtonParser()
    parser.feed(html)
    return parser.buttons[control_class]


def _mock_manager(*, with_collector: bool = False) -> MagicMock:
    manager = MagicMock()
    manager.collectors = []
    manager.collector_health = {}
    manager.skipped_collectors = []
    manager.is_collector_running.return_value = False
    manager.get_collector_by_name.return_value = None
    manager.get_collector_by_class_name.return_value = None
    manager.get_scheduling_diagnostics.return_value = {
        "collectors": [],
        "smoothing": {
            "enabled": False,
            "window_ratio": 0.3,
            "min_batch_delay": 0.1,
            "max_batch_delay": 2.0,
            "window_cap_seconds": 230.0,
        },
        "collector_timeout_seconds": 240,
        "rate_limiter": {
            "enabled": False,
            "rps": 10,
            "burst": 5,
            "share_fraction": 0.5,
        },
        "scheduler": {},
    }
    if with_collector:
        collector = MagicMock()
        collector.__class__ = type("DeviceCollector", (), {})
        collector.is_active = True
        collector.collector_cadence_seconds.return_value = 300.0
        manager.collectors = [collector]
        manager.collector_health = {
            "DeviceCollector": {
                "total_runs": 0,
                "total_successes": 0,
                "failure_streak": 0,
                "last_success_time": None,
            }
        }
    return manager


@pytest.fixture
def exporter_factory(test_settings: Settings) -> Callable[[], ExporterApp]:
    """Build app instances without constructing the unrelated Meraki SDK facade."""

    def build() -> ExporterApp:
        with patch.object(
            AsyncMerakiClient,
            "api",
            new_callable=PropertyMock,
            return_value=MagicMock(),
        ):
            return ExporterApp(test_settings)

    return build


@pytest.fixture
def control_client(exporter_factory: Callable[[], ExporterApp]) -> tuple[TestClient, MagicMock]:
    """Build a control-endpoint client with the default unset API token."""
    exporter = exporter_factory()
    manager = _mock_manager()
    exporter.collector_manager = manager
    return TestClient(exporter.create_app(), raise_server_exceptions=False), manager


@pytest.fixture
def test_settings() -> Settings:
    """Build minimal settings with no configured control API token."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        )
    )


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/collectors/trigger", {"collector": "DeviceCollector"}),
        ("/api/clients/clear-dns-cache", None),
    ],
)
def test_control_posts_fail_closed_without_api_token(
    control_client: tuple[TestClient, MagicMock],
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    """An unset server.api_token must reject both mutating routes before dispatch."""
    client, manager = control_client

    response = client.post(path, json=payload)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API token"}
    manager.get_collector_by_name.assert_not_called()
    manager.get_collector_by_class_name.assert_not_called()


def test_malformed_trigger_fails_authentication_before_body_validation(
    control_client: tuple[TestClient, MagicMock],
) -> None:
    """An unauthenticated malformed trigger must not expose a pre-auth 422 path."""
    client, manager = control_client

    response = client.post("/api/collectors/trigger", content=b"not-json")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API token"}
    manager.get_collector_by_name.assert_not_called()


def test_empty_api_token_cannot_authenticate_control_posts(
    test_settings: Settings,
    exporter_factory: Callable[[], ExporterApp],
) -> None:
    """A blank SecretStr cannot compare equal to an empty Bearer credential."""
    test_settings.server.api_token = SecretStr("")
    exporter = exporter_factory()
    manager = _mock_manager(with_collector=True)
    exporter.collector_manager = manager
    client = TestClient(exporter.create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/collectors/trigger",
        json={"collector": "DeviceCollector"},
        headers={"Authorization": "Bearer "},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API token"}
    manager.get_collector_by_name.assert_not_called()


def test_blank_api_token_configuration_normalizes_to_unset() -> None:
    """Whitespace-only control tokens retain the fail-closed unset posture."""
    settings = Settings.model_validate({
        "meraki": {"api_key": "a" * 40},
        "server": {"api_token": "   "},
    })

    assert settings.server.api_token is None


def test_index_disables_manual_trigger_without_api_token(
    exporter_factory: Callable[[], ExporterApp],
) -> None:
    """The landing page explains why manual collector triggers are unavailable."""
    exporter = exporter_factory()
    exporter.collector_manager = _mock_manager(with_collector=True)
    client = TestClient(exporter.create_app(), raise_server_exceptions=True)

    response = client.get("/")

    assert response.status_code == 200
    attributes = _control_attributes(response.text, "collector-trigger")
    assert "disabled" in attributes
    assert attributes["title"] == CONTROL_DISABLED_TOOLTIP


def test_clients_page_disables_dns_clear_without_api_token(
    test_settings: Settings,
    exporter_factory: Callable[[], ExporterApp],
) -> None:
    """The clients page explains why DNS cache mutation is unavailable."""
    test_settings.clients.enabled = True
    exporter = exporter_factory()
    manager = _mock_manager()
    client_store = MagicMock()
    client_store.get_all_clients.return_value = []
    client_store.get_statistics.return_value = {
        "total_clients": 0,
        "online_clients": 0,
        "offline_clients": 0,
        "total_networks": 0,
    }
    dns_resolver = MagicMock()
    dns_resolver.get_cache_stats.return_value = {
        "total_entries": 0,
        "valid_entries": 0,
        "expired_entries": 0,
        "tracked_clients": 0,
        "cache_ttl_seconds": 300,
    }
    clients_collector = MagicMock()
    clients_collector.is_active = True
    clients_collector.client_store = client_store
    clients_collector.dns_resolver = dns_resolver
    manager.get_collector_by_class_name.return_value = clients_collector
    exporter.collector_manager = manager
    client = TestClient(exporter.create_app(), raise_server_exceptions=True)

    response = client.get("/clients")

    assert response.status_code == 200
    attributes = _control_attributes(response.text, "clear-cache-btn")
    assert "disabled" in attributes
    assert attributes["title"] == CONTROL_DISABLED_TOOLTIP
