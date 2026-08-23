"""Shared test fixtures and configuration."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY, CollectorRegistry


class _ImmediateFacadeLimiter:
    """No-delay limiter for legacy unit constructions that do not wire the app graph."""

    async def acquire(self, org_id: str | None, operation: str) -> float:
        """Admit immediately while preserving the facade's pacing call shape."""
        return 0.0

    def record_throttle_event(self, org_id: str | None, retry_after: float | None) -> None:
        """Accept retry feedback without adding timing to unit tests."""


@pytest.fixture(autouse=True)
def default_facade_limiter_for_tests(monkeypatch, request):
    """Supply pacing to lightweight tests that do not construct the production owner graph.

    Tests marked ``strict_facade_limiter`` opt out so the production fail-closed contract remains
    directly exercised. Explicit limiter doubles supplied by a test always take precedence.
    """
    if request.node.get_closest_marker("strict_facade_limiter") is not None:
        yield
        return

    from meraki_dashboard_exporter.core.api_facade import MerakiApiFacade

    original_init = MerakiApiFacade.__init__

    def init_with_test_limiter(self, *, settings=None, rate_limiter=None):
        if rate_limiter is None:
            rate_limiter = _ImmediateFacadeLimiter()
            api_settings = getattr(settings, "api", None)
            max_retries = getattr(api_settings, "max_retries", None)
            if api_settings is not None and not isinstance(max_retries, int | float):
                api_settings.max_retries = 0
        original_init(self, settings=settings, rate_limiter=rate_limiter)

    monkeypatch.setattr(MerakiApiFacade, "__init__", init_with_test_limiter)
    yield


@pytest.fixture(autouse=True)
def fast_test_settings(monkeypatch):
    """Disable production timing features that slow down tests."""
    monkeypatch.setenv("MERAKI_EXPORTER_API__SMOOTHING_ENABLED", "false")
    monkeypatch.setenv("MERAKI_EXPORTER_API__MAX_RETRIES", "0")


@pytest.fixture(autouse=True)
def clean_prometheus_registry():
    """Clean the Prometheus registry before and after each test."""
    # Store current collectors
    collectors = list(REGISTRY._collector_to_names.keys())

    # Clear the registry
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass

    yield

    # Clear again after test
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass


@pytest.fixture
def isolated_registry():
    """Create an isolated Prometheus registry for tests."""
    registry = CollectorRegistry()
    yield registry
    # Registry will be garbage collected after test


@pytest.fixture(autouse=True)
def reset_client_auth_state():
    """Reset the AsyncMerakiClient auth-outcome latch around every test (#509)."""
    from meraki_dashboard_exporter.api.client import AsyncMerakiClient

    AsyncMerakiClient.reset_auth_state()
    yield
    AsyncMerakiClient.reset_auth_state()


@pytest.fixture
def force_debug_log_capture():
    """Force structlog to emit DEBUG events so ``capture_logs()`` can record them.

    Other tests invoke the app's ``setup_logging`` (an INFO-filtering bound
    logger) whose config leaks globally, dropping ``logger.debug()`` calls
    before ``structlog.testing.capture_logs`` sees them. This snapshots the
    current config, installs a DEBUG-level bound logger for the test, and
    restores the prior config afterwards so nothing leaks onward.
    """
    import logging

    import structlog

    prev = structlog.get_config()
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG))
    try:
        yield
    finally:
        structlog.configure(**prev)
