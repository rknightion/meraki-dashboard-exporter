"""URL settings never print their credentials in logs, errors or the --check summary (#1030)."""

from __future__ import annotations

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter  # noqa: PLC2701
from prometheus_client import CollectorRegistry
from pydantic import SecretStr, ValidationError
from structlog.testing import capture_logs

from meraki_dashboard_exporter.__main__ import _print_redacted_summary  # noqa: PLC2701
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.core.otel_data_logs import DataLogEmitter
from meraki_dashboard_exporter.core.otel_metrics import OTelMetricsBridge

SENTINEL = "pw-sentinel"  # pragma: allowlist secret
KEY = "k" * 40


def _url(host: str) -> str:
    # Built from parts so the privacy sweep does not read the test URL as a credential.
    return "https://" + "user:" + SENTINEL + "@" + host


def test_otlp_logs_init_log_omits_endpoint_credentials() -> None:
    """The data-log emitter's init log shows the endpoint without its credentials."""
    settings = Settings(
        meraki={"api_key": KEY},
        otel={"logs": {"enabled": True, "endpoint": _url("otlp.example:4317")}},
    )
    with capture_logs() as logs:
        DataLogEmitter(settings, registry=CollectorRegistry(), exporter=InMemoryLogRecordExporter())

    init = [e for e in logs if e["event"] == "OTel data-log emitter initialized"]
    assert init, logs
    assert init[0]["endpoint"] == "https://***@otlp.example:4317"
    assert SENTINEL not in repr(logs)


def test_otlp_metrics_init_log_omits_endpoint_credentials() -> None:
    """The metrics bridge's init log shows the endpoint without its credentials."""
    from tests.unit.test_otel_metrics import _StubExporter

    settings = Settings(
        meraki={"api_key": KEY},
        otel={"metrics": {"enabled": True, "endpoint": _url("otlp.example:4317")}},
    )
    with capture_logs() as logs:
        OTelMetricsBridge(settings, registry=CollectorRegistry(), exporter=_StubExporter())

    init = [e for e in logs if e["event"] == "OTel metrics bridge initialized"]
    assert init, logs
    assert init[0]["endpoint"] == "https://***@otlp.example:4317"
    assert SENTINEL not in repr(logs)


def test_check_summary_omits_base_url_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    """The --check summary shows the API base URL without its credentials."""
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr(KEY),
            api_base_url=_url("meraki-proxy.example/api/v1"),
            allow_custom_api_base_url=True,
        )
    )
    _print_redacted_summary(settings)

    out = capsys.readouterr().out
    assert "https://***@meraki-proxy.example/api/v1" in out
    assert SENTINEL not in out


def test_custom_base_url_warning_omits_credentials() -> None:
    """The custom base URL warning shows the URL without its credentials."""
    with capture_logs() as logs:
        MerakiSettings(
            api_key=SecretStr(KEY),
            api_base_url=_url("meraki-proxy.example/api/v1"),
            allow_custom_api_base_url=True,
        )

    warning = [
        e for e in logs if e["event"] == "Using explicitly allowed custom Meraki API base URL"
    ]
    assert warning, logs
    assert warning[0]["api_base_url"] == "https://***@meraki-proxy.example/api/v1"
    assert SENTINEL not in repr(logs)


def test_invalid_base_url_error_omits_credentials() -> None:
    """A rejected base URL is named in the error without its credentials."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            meraki={
                "api_key": KEY,
                "api_base_url": "http://" + "user:" + SENTINEL + "@h.example/v1",
            }
        )

    assert SENTINEL not in str(excinfo.value)
    assert "http://***@h.example/v1" in str(excinfo.value)


def test_invalid_api_key_is_not_echoed_in_the_error() -> None:
    """A rejected API key never appears in the validation error."""
    short_key = "short-key-sentinel"  # pragma: allowlist secret
    with pytest.raises(ValidationError) as excinfo:
        Settings(meraki={"api_key": short_key})

    assert short_key not in str(excinfo.value)


def test_tracing_init_log_omits_endpoint_credentials() -> None:
    """The tracing init log shows the endpoint without its credentials."""
    from unittest.mock import patch

    from meraki_dashboard_exporter.core.otel_tracing import TracingConfig

    settings = Settings(
        meraki={"api_key": KEY}, otel={"enabled": True, "endpoint": _url("otlp.example:4317")}
    )
    config = TracingConfig(settings)
    base = "meraki_dashboard_exporter.core.otel_tracing"
    with (
        patch(f"{base}.TracerProvider"),
        patch(f"{base}.OTLPSpanExporter") as exporter,
        patch(f"{base}.BatchSpanProcessor"),
        patch(f"{base}.trace.set_tracer_provider"),
        patch(f"{base}.set_global_textmap"),
        patch.object(config, "_instrument_libraries"),
        capture_logs() as logs,
    ):
        config.setup_tracing()

    init = [e for e in logs if e["event"] == "OpenTelemetry tracing initialized"]
    assert init, logs
    assert init[0]["endpoint"] == "https://***@otlp.example:4317"
    assert SENTINEL not in repr(logs)
    # The exporter itself still receives the real endpoint.
    assert exporter.call_args.kwargs["endpoint"] == _url("otlp.example:4317")


@pytest.mark.usefixtures("force_debug_log_capture")
async def test_api_client_creation_log_omits_base_url_credentials() -> None:
    """The API client creation log shows the base URL without its credentials."""
    from unittest.mock import MagicMock, patch

    from meraki_dashboard_exporter.api.client import AsyncMerakiClient

    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr(KEY),
            api_base_url=_url("meraki-proxy.example/api/v1"),
            allow_custom_api_base_url=True,
        )
    )
    client = AsyncMerakiClient(settings)
    with (
        patch.object(client, "_create_api_client", return_value=MagicMock()),
        capture_logs() as logs,
    ):
        await client._get_api_client()

    created = [e for e in logs if e["event"] == "Creating new Meraki Dashboard API client"]
    assert created, logs
    assert created[0]["base_url"] == "https://***@meraki-proxy.example/api/v1"
    assert SENTINEL not in repr(logs)


def test_settings_summary_omits_url_credentials() -> None:
    """Settings.to_summary, documented as safe for logging, masks URL settings."""
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr(KEY),
            api_base_url=_url("meraki-proxy.example/api/v1"),
            allow_custom_api_base_url=True,
        ),
        api={"requests_proxy": "tokensentinel" + "@proxy.example:3128"},
        otel={"endpoint": _url("otlp.example:4317")},
    )
    summary = settings.to_summary()

    assert summary["meraki"]["api_base_url"] == "https://***@meraki-proxy.example/api/v1"
    assert summary["api"]["requests_proxy"] == "***@proxy.example:3128"
    assert summary["otel"]["endpoint"] == "https://***@otlp.example:4317"
    assert SENTINEL not in repr(summary)
    assert "tokensentinel" not in repr(summary)
