---
type: C4 Component
title: Logging (core/logging*.py)
status: stable
groma:
  id: logging
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/logging.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/logging_helpers.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/logging_decorators.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/otel_logging.py
  technology: Python, structlog
  group: Self-observability
description: Structured logging, logging decorators and trace-context injection
---

Configures structlog output on stdout, provides the `log_api_call` and progress decorators and shared helpers collectors use for consistent log lines, and adds trace and span IDs to log records when tracing is on. Application logs are not exported over OTLP.
