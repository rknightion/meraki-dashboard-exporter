"""Tests for core.logging renderer selection (log_format setting, #310)."""

from __future__ import annotations

import structlog

from meraki_dashboard_exporter.core.logging import _select_renderer  # noqa: PLC2701


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
