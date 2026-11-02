---
type: C4 Component
title: Network filter (core/network_filter.py)
status: stable
groma:
  id: network-filter
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/network_filter.py
  technology: Python
  group: Collection runtime
description: Decides which networks are collected
---

Pure logic over `NetworkFilterSettings`: given a list of networks, returns those to collect. No I/O and no caching; the inventory service applies it on every read.
