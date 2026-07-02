"""Tests for the webhook body byte-cap guard (F-103).

The webhook receiver must enforce a hard byte cap while *reading* the request
body, regardless of the ``Content-Length`` header. A ``Transfer-Encoding:
chunked`` request (or any request that omits ``Content-Length``) must not be
able to buffer an unbounded body before the shared secret is validated.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings, WebhookSettings


@pytest.fixture
def webhook_settings_small_cap() -> Settings:
    """Webhooks enabled with a small (1 KiB) payload cap."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
        webhooks=WebhookSettings(
            enabled=True,
            shared_secret=SecretStr("test_secret"),
            require_secret=True,
            max_payload_size=1024,
        ),
    )


@pytest.fixture
def webhook_client(webhook_settings_small_cap: Settings) -> TestClient:
    """TestClient for the webhook-enabled app."""
    exporter = ExporterApp(webhook_settings_small_cap)
    app = exporter.create_app()
    return TestClient(app, raise_server_exceptions=False)


def _chunked_body(total_bytes: int, chunk: int = 256) -> Iterator[bytes]:
    """Yield ``total_bytes`` of JSON-ish payload in chunks (chunked encoding).

    Passing a sync iterator as the httpx request ``content`` triggers
    ``Transfer-Encoding: chunked`` with NO ``Content-Length`` header, which is
    exactly the case the header-only guard used to miss.
    """
    remaining = total_bytes
    # Start with a valid-looking JSON opener so we know rejection is on size,
    # not on JSON parsing.
    opener = b'{"data": "'
    yield opener
    remaining -= len(opener)
    while remaining > 0:
        n = min(chunk, remaining)
        yield b"x" * n
        remaining -= n


class TestWebhookBodySizeCap:
    """The streaming byte cap rejects oversize bodies before secret handling."""

    def test_chunked_body_over_cap_returns_413(self, webhook_client: TestClient) -> None:
        """A chunked body (no Content-Length) over the cap is rejected with 413."""
        response = webhook_client.post(
            "/api/webhooks/meraki",
            content=_chunked_body(4096),  # 4 KiB > 1 KiB cap
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    def test_chunked_body_over_cap_has_no_content_length(self, webhook_client: TestClient) -> None:
        """Sanity: the guard fires even though the request omits Content-Length.

        We build the request explicitly so we can assert Content-Length is not
        present - proving the streaming counter, not the header check, does the
        work.
        """
        request = webhook_client.build_request(
            "POST",
            "/api/webhooks/meraki",
            content=_chunked_body(4096),
            headers={"Content-Type": "application/json"},
        )
        assert "content-length" not in {k.lower() for k in request.headers}
        response = webhook_client.send(request)
        assert response.status_code == 413

    def test_records_validation_failure_metric(self, webhook_settings_small_cap: Settings) -> None:
        """An oversize chunked body increments the payload_too_large counter."""
        exporter = ExporterApp(webhook_settings_small_cap)
        app = exporter.create_app()
        client = TestClient(app, raise_server_exceptions=False)

        assert exporter.webhook_handler is not None
        counter = exporter.webhook_handler.validation_failures.labels(
            validation_error="payload_too_large"
        )
        before = counter._value.get()

        response = client.post(
            "/api/webhooks/meraki",
            content=_chunked_body(4096),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert counter._value.get() == before + 1

    def test_small_chunked_body_is_processed(self, webhook_client: TestClient) -> None:
        """A valid, under-cap chunked body still flows through to processing.

        It has a wrong/missing secret so it ends at 401 (validation), proving
        the body was read and handed to the handler rather than rejected on size.
        """

        def small_json() -> Iterator[bytes]:
            yield b'{"version": "1.0"}'

        response = webhook_client.post(
            "/api/webhooks/meraki",
            content=small_json(),
            headers={"Content-Type": "application/json"},
        )
        # Under the cap -> reaches the handler; invalid payload -> 401, not 413.
        assert response.status_code == 401
