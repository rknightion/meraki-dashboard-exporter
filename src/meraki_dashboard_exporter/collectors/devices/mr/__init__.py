"""Meraki MR (Wireless AP) metrics collectors.

This package contains modular collectors for MR device metrics:
- clients: Client connection and authentication metrics (✅ COMPLETE)
- performance: Ethernet status, packet loss, CPU metrics (✅ COMPLETE)
- wireless: SSID status, radio configuration, usage metrics (✅ COMPLETE)
- collector: Main coordinator that delegates to sub-collectors (✅ COMPLETE)

Phase 3.1 Status:
- ✅ Pattern established following Phase 3.2 metric expiration integration
- ✅ Reference implementation: clients.py (271 lines)
- ✅ Performance collector: performance.py (1,022 lines)
- ✅ Wireless collector: wireless.py (474 lines)
- ✅ Coordinator: collector.py (fully integrated)

All collectors follow the P3.2 pattern using `self.parent._set_metric()` for
automatic metric expiration tracking.
"""

from __future__ import annotations

from .collector import MRCollector

__all__ = ["MRCollector"]
