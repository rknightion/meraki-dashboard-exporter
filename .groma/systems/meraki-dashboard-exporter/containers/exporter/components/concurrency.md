---
type: C4 Component
title: Concurrency helpers
status: stable
groma:
  id: concurrency
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/async_utils.py
    - scanner: python
      file: src/meraki_dashboard_exporter/core/batch_processing.py
  technology: Python
  group: Collection runtime
description: ManagedTaskGroup, retry helpers and batch processing
---

`ManagedTaskGroup` and `process_in_batches_with_errors` are the sanctioned ways to fan out work; raw `asyncio.gather` is not used in collectors. Also holds async retry and executor shutdown helpers.
