"""Tests for span_metrics module.

The span metrics functionality was removed as it is redundant with tracing
backend capabilities. This file documents that the module is intentionally empty.
"""

# ruff: noqa: S101

from __future__ import annotations


def test_span_metrics_module_is_deprecated() -> None:
    """Verify the span_metrics module is empty (deprecated).

    The SpanMetricsProcessor and SpanMetricsAggregator classes were removed
    because they duplicate functionality provided by tracing backends like
    Jaeger, Tempo, and Datadog that can generate metrics from traces natively.
    """
    from meraki_dashboard_exporter.core import span_metrics

    # Module should only have standard attributes (no classes or functions)
    public_attrs = [attr for attr in dir(span_metrics) if not attr.startswith("_")]
    # Only annotations should be present
    assert public_attrs in (["annotations"], [])
