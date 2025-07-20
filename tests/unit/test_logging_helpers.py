"""Tests for logging helpers functions."""

# ruff: noqa: S101

import structlog

from meraki_dashboard_exporter.core import logging_helpers as lh


def test_format_bytes_and_duration():
    """Verify human-readable formatting utilities."""
    assert lh.format_bytes(512) == "512.0 B"
    assert lh.format_bytes(1024) == "1.0 KB"
    assert lh.format_bytes(1536) == "1.5 KB"

    assert lh.format_duration(0.5) == "500ms"
    assert lh.format_duration(10) == "10.0s"
    assert lh.format_duration(90) == "1m 30s"
    assert lh.format_duration(3600 + 120) == "1h 2m"


def test_log_context_binds_and_unbinds(monkeypatch):
    """Ensure LogContext binds and unbinds values."""
    calls: list[tuple[str, object]] = []

    def fake_bind(**kwargs):
        calls.append(("bind", kwargs))
        return object()

    def fake_unbind(*args):
        calls.append(("unbind", args))

    monkeypatch.setattr(structlog.contextvars, "bind_contextvars", fake_bind)
    monkeypatch.setattr(structlog.contextvars, "unbind_contextvars", fake_unbind)

    with lh.LogContext(example="value"):
        pass

    assert calls == [("bind", {"example": "value"}), ("unbind", ("example",))]


def test_log_with_context_passes_values(monkeypatch):
    """log_with_context should forward context to logger."""
    recorded = {}

    def fake_log(message, **kwargs):
        recorded["msg"] = message
        recorded.update(kwargs)

    monkeypatch.setattr(lh.logger, "info", fake_log)
    lh.log_with_context("info", "message", collector="c1", extra="x")
    assert recorded == {"msg": "message", "collector": "c1", "extra": "x"}
