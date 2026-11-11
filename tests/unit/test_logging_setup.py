"""Tests for core.logging renderer selection and exception rendering."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from meraki_dashboard_exporter.core import logging as core_logging
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.logging import _select_renderer  # noqa: PLC2701

_SENTINEL = "local-sentinel-value-0123456789"

# Every stdlib logger setup_logging reconfigures, so the test can put them back.
_TOUCHED_LOGGERS = (
    "",
    "urllib3",
    "requests",
    "asyncio",
    "opentelemetry",
    "opentelemetry.sdk",
    "opentelemetry.instrumentation",
    "opentelemetry.exporter",
    "meraki",
    "httpx",
    "httpcore",
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
)


class TestSelectRenderer:
    """Tests for the _select_renderer helper (#310)."""

    def test_json_selects_json_renderer(self) -> None:
        """log_format='json' selects structlog's JSONRenderer."""
        renderer = _select_renderer("json")
        assert isinstance(renderer, structlog.processors.JSONRenderer)

    def test_logfmt_selects_logfmt_renderer(self) -> None:
        """log_format='logfmt' selects structlog's LogfmtRenderer."""
        renderer = _select_renderer("logfmt")
        assert isinstance(renderer, structlog.processors.LogfmtRenderer)

    def test_default_is_logfmt(self) -> None:
        """An unknown/empty value falls back to logfmt (backward-compatible default)."""
        assert isinstance(_select_renderer(""), structlog.processors.LogfmtRenderer)
        assert isinstance(_select_renderer("unexpected"), structlog.processors.LogfmtRenderer)

    def test_case_insensitive(self) -> None:
        """The format token is matched case-insensitively."""
        assert isinstance(_select_renderer("JSON"), structlog.processors.JSONRenderer)


@pytest.fixture
def fresh_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Let setup_logging run again, and undo its global changes afterwards."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setattr(core_logging, "_LOGGING_CONFIGURED", False)
    prev_structlog = structlog.get_config()
    prev_loggers = {}
    for name in _TOUCHED_LOGGERS:
        logger = logging.getLogger(name)
        prev_loggers[name] = (logger.level, list(logger.handlers), logger.propagate)
    try:
        yield
    finally:
        structlog.configure(**prev_structlog)
        for name, (level, handlers, propagate) in prev_loggers.items():
            logger = logging.getLogger(name)
            logger.setLevel(level)
            logger.handlers[:] = handlers
            logger.propagate = propagate


def _raise_with_secret_local() -> None:
    held_secret = _SENTINEL
    raise ValueError("boom " + str(len(held_secret)))


class TestExceptionRendering:
    """Logged exceptions carry the traceback but never the frames' local variables."""

    @pytest.mark.parametrize("log_format", ["json", "logfmt"])
    def test_logged_exception_omits_frame_locals(
        self,
        fresh_logging: None,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        log_format: str,
    ) -> None:
        """A local holding a secret never reaches the log through the real processor chain."""
        monkeypatch.setenv("MERAKI_EXPORTER_LOGGING__LOG_FORMAT", log_format)
        core_logging.setup_logging(Settings())
        logger = core_logging.get_logger("test.exception_rendering")

        try:
            _raise_with_secret_local()
        except ValueError:
            logger.exception("helper failed")

        out = capsys.readouterr().out
        assert "helper failed" in out
        assert "_raise_with_secret_local" in out, "the traceback should still be logged"
        assert _SENTINEL not in out
        # The key, quoted as each renderer quotes it (the test's own name contains the word).
        assert '"locals"' not in out
        assert "'locals'" not in out
        if log_format == "json":
            event = json.loads(out.strip().splitlines()[-1])
            frames = [frame for exc in event["exception"] for frame in exc["frames"]]
            assert frames
            assert all("locals" not in frame for frame in frames)
