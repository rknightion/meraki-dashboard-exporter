"""Span metrics module - deprecated and removed.

The span metrics functionality (SpanMetricsProcessor, SpanMetricsAggregator) has been
removed as it is redundant with tracing backend capabilities. Most tracing backends
(Jaeger, Grafana Tempo, Datadog, New Relic) provide built-in metrics generation from
traces, making in-application RED metrics generation unnecessary.

Users who need trace-derived metrics should configure their tracing backend's
metrics generation feature instead.
"""

from __future__ import annotations

# This module is intentionally empty.
# Span metrics functionality was removed as redundant.
# See module docstring for details.
