"""Shared test fixtures and configuration."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY, CollectorRegistry


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
