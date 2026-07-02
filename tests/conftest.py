"""Shared test fixtures and configuration."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY, CollectorRegistry

pytest_plugins = ["tests.fixtures.large_org"]


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
