"""Rendered control-UI regression coverage for #725."""

from __future__ import annotations

from html.parser import HTMLParser
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from meraki_dashboard_exporter.api.client import AsyncMerakiClient
from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings


class _ControlButtonParser(HTMLParser):
    """Collect the classes of rendered control buttons."""

    def __init__(self) -> None:
        super().__init__()
        self.classes: set[str] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag == "button":
            self.classes.update((dict(attrs).get("class") or "").split())


def _manager() -> MagicMock:
    manager = MagicMock()
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
    manager.skipped_collectors = []
    manager.is_collector_running.return_value = False
    manager.get_scheduling_diagnostics.return_value = {
        "collectors": [],
        "smoothing": {},
        "collector_timeout_seconds": 240,
        "rate_limiter": {},
        "scheduler": {},
    }
    return manager


def _clients_collector() -> MagicMock:
    collector = MagicMock()
    collector.is_active = True
    collector.client_store.get_all_clients.return_value = []
    collector.client_store.get_statistics.return_value = {
        "total_clients": 0,
        "online_clients": 0,
        "offline_clients": 0,
        "total_networks": 0,
    }
    collector.dns_resolver.get_cache_stats.return_value = {
        "total_entries": 0,
        "valid_entries": 0,
        "expired_entries": 0,
        "tracked_clients": 0,
        "cache_ttl_seconds": 300,
    }
    return collector


@pytest.mark.parametrize("api_token", [None, "test-control-token"])
def test_control_buttons_match_the_token_state(
    api_token: str | None,
) -> None:
    """#725: unset controls stay disabled; configured controls are API-only."""
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        )
    )
    settings.clients.enabled = True
    if api_token is not None:
        settings.server.api_token = SecretStr(api_token)

    with patch.object(
        AsyncMerakiClient,
        "api",
        new_callable=PropertyMock,
        return_value=MagicMock(),
    ):
        exporter = ExporterApp(settings)
    manager = _manager()
    manager.get_collector_by_class_name.return_value = _clients_collector()
    exporter.collector_manager = manager
    client = TestClient(exporter.create_app(), raise_server_exceptions=True)
    headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}

    for path, control_class in (("/", "collector-trigger"), ("/clients", "clear-cache-btn")):
        response = client.get(path, headers=headers)
        parser = _ControlButtonParser()
        parser.feed(response.text)

        assert response.status_code == 200
        assert (control_class not in parser.classes) is (api_token is not None)
        if api_token is not None:
            assert api_token not in response.text
