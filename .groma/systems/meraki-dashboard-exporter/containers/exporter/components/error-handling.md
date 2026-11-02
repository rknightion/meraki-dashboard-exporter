---
type: C4 Component
title: Error handling (core/error_handling.py)
status: stable
groma:
  id: error-handling
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/error_handling.py
  technology: Python
  group: Meraki API access
description: Fetcher decorators, error categories and response validation
---

`@with_error_handling` categorises and records failures and can continue past them; `validate_response_format` checks a response's shape, unwraps `{"items": [...]}` and turns the SDK's exhausted-retry error shape into an exception instead of data. Every new fetcher is wrapped with it.
