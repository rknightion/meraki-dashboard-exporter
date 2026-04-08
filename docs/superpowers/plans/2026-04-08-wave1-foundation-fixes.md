# Wave 1: Foundation Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all known bugs and code inconsistencies in the Meraki Dashboard Exporter so subsequent improvement waves build on solid ground.

**Architecture:** Fix 5 Python exception syntax bugs, 3 metric naming mismatches, 3 unbounded caches, 1 dead code path, consolidate 5 `_set_metric_value` implementations into 2, refactor MTCollector dual mode via factory pattern, standardize error handling conventions, and relocate misplaced port overview metrics.

**Tech Stack:** Python 3.14, Prometheus client, Pydantic, pytest, ruff, mypy

**Spec:** `docs/superpowers/specs/2026-04-08-comprehensive-improvement-roadmap-design.md` (Wave 1 section)

---

### Task 1: Fix Python 2 Exception Syntax

**Files:**
- Modify: `src/meraki_dashboard_exporter/core/error_handling.py:493,502`
- Modify: `src/meraki_dashboard_exporter/api/client.py:339`
- Modify: `src/meraki_dashboard_exporter/core/api_helpers.py:374`
- Modify: `src/meraki_dashboard_exporter/core/collector.py:454`
- Test: `tests/unit/test_exception_syntax.py`

- [ ] **Step 1: Write a test that catches the incorrect exception handling**

Create `tests/unit/test_exception_syntax.py`:

```python
"""Tests for correct exception handling syntax across the codebase."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


KNOWN_EXCEPTION_FILES = [
    "src/meraki_dashboard_exporter/core/error_handling.py",
    "src/meraki_dashboard_exporter/api/client.py",
    "src/meraki_dashboard_exporter/core/api_helpers.py",
    "src/meraki_dashboard_exporter/core/collector.py",
]


@pytest.mark.parametrize("filepath", KNOWN_EXCEPTION_FILES)
def test_no_python2_except_syntax(filepath: str) -> None:
    """Verify no except clauses use comma syntax (except X, Y:).

    Python 3 requires except (X, Y): for multiple exceptions.
    The comma syntax silently catches only the first type and
    assigns the second as the exception variable.
    """
    source = Path(filepath).read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            # ExceptHandler.type should be a Tuple for multi-exception
            # or a Name for single exception. If it's a Name and the
            # handler has a `name` that matches a builtin exception,
            # that's the bug pattern.
            if (
                node.name is not None
                and node.type is not None
                and isinstance(node.type, ast.Name)
                and node.name in {"ValueError", "TypeError", "AttributeError", "ImportError"}
            ):
                pytest.fail(
                    f"{filepath}:{node.lineno} - except {node.type.id}, {node.name}: "
                    f"uses Python 2 comma syntax. Should be except ({node.type.id}, {node.name}):"
                )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_exception_syntax.py -v`
Expected: FAIL on all 4 files (5 instances total)

- [ ] **Step 3: Fix error_handling.py - two instances**

In `src/meraki_dashboard_exporter/core/error_handling.py`, change line 493:
```python
# Before:
        except TypeError, ValueError:
# After:
        except (TypeError, ValueError):
```

And line 502:
```python
# Before:
        except TypeError, ValueError:
# After:
        except (TypeError, ValueError):
```

- [ ] **Step 4: Fix client.py**

In `src/meraki_dashboard_exporter/api/client.py`, change line 339:
```python
# Before:
                except TypeError, ValueError:
# After:
                except (TypeError, ValueError):
```

- [ ] **Step 5: Fix api_helpers.py**

In `src/meraki_dashboard_exporter/core/api_helpers.py`, change line 374:
```python
# Before:
        except TypeError, ValueError:
# After:
        except (TypeError, ValueError):
```

- [ ] **Step 6: Fix collector.py**

In `src/meraki_dashboard_exporter/core/collector.py`, change line 454:
```python
# Before:
        except ImportError, AttributeError:
# After:
        except (ImportError, AttributeError):
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_exception_syntax.py -v`
Expected: PASS for all 4 files

- [ ] **Step 8: Run full linting and type check**

Run: `uv run ruff check src/meraki_dashboard_exporter/core/error_handling.py src/meraki_dashboard_exporter/api/client.py src/meraki_dashboard_exporter/core/api_helpers.py src/meraki_dashboard_exporter/core/collector.py && uv run mypy src/meraki_dashboard_exporter/core/error_handling.py src/meraki_dashboard_exporter/api/client.py src/meraki_dashboard_exporter/core/api_helpers.py src/meraki_dashboard_exporter/core/collector.py`
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add tests/unit/test_exception_syntax.py src/meraki_dashboard_exporter/core/error_handling.py src/meraki_dashboard_exporter/api/client.py src/meraki_dashboard_exporter/core/api_helpers.py src/meraki_dashboard_exporter/core/collector.py
git commit -m "fix: replace Python 2 exception syntax with tuple form

5 instances across 4 files used 'except X, Y:' (Python 2) instead of
'except (X, Y):' (Python 3). The comma syntax catches only the first
exception type and binds the second as the variable name, causing
some exceptions to bypass retry logic entirely."
```

---

### Task 2: Fix Metric Enum Naming

**Files:**
- Modify: `src/meraki_dashboard_exporter/core/constants/metrics_constants.py:99-102`
- Modify: `src/meraki_dashboard_exporter/collectors/devices/ms.py:135,152,182`
- Modify: `dashboards/ms-switches.json` (no code changes, just verify metric names)
- Test: `tests/unit/test_metrics_constants.py`

- [ ] **Step 1: Write a test for enum name/value consistency**

Create `tests/unit/test_metrics_constants.py`:

```python
"""Tests for metric constant naming consistency."""

from __future__ import annotations

import pytest

from meraki_dashboard_exporter.core.constants.metrics_constants import MSMetricName


class TestMSMetricNaming:
    """Verify MS metric enum names match their string values."""

    @pytest.mark.parametrize(
        "enum_member,expected_unit",
        [
            ("MS_POE_PORT_POWER_WATTHOURS", "watthours"),
            ("MS_POE_TOTAL_POWER_WATTHOURS", "watthours"),
            ("MS_POE_NETWORK_TOTAL_WATTHOURS", "watthours"),
            ("MS_POE_BUDGET_WATTS", "watts"),
            ("MS_POWER_USAGE_WATTS", "watts"),
        ],
    )
    def test_poe_metric_unit_consistency(self, enum_member: str, expected_unit: str) -> None:
        """Verify POE metric enum names match their string value units."""
        member = MSMetricName[enum_member]
        assert expected_unit in member.value, (
            f"Enum {enum_member} value '{member.value}' does not contain expected unit '{expected_unit}'"
        )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_metrics_constants.py -v`
Expected: FAIL - `MSMetricName` has no member `MS_POE_PORT_POWER_WATTHOURS`

- [ ] **Step 3: Rename the enum members**

In `src/meraki_dashboard_exporter/core/constants/metrics_constants.py`, change lines 99-102:

```python
# Before:
    MS_POE_PORT_POWER_WATTS = "meraki_ms_poe_port_power_watthours"  # Actually Wh not W
    MS_POE_TOTAL_POWER_WATTS = "meraki_ms_poe_total_power_watthours"  # Actually Wh not W
    MS_POE_BUDGET_WATTS = "meraki_ms_poe_budget_watts"
    MS_POE_NETWORK_TOTAL_WATTS = "meraki_ms_poe_network_total_watthours"  # Actually Wh not W

# After:
    MS_POE_PORT_POWER_WATTHOURS = "meraki_ms_poe_port_power_watthours"
    MS_POE_TOTAL_POWER_WATTHOURS = "meraki_ms_poe_total_power_watthours"
    MS_POE_BUDGET_WATTS = "meraki_ms_poe_budget_watts"
    MS_POE_NETWORK_TOTAL_WATTHOURS = "meraki_ms_poe_network_total_watthours"
```

- [ ] **Step 4: Update references in ms.py**

In `src/meraki_dashboard_exporter/collectors/devices/ms.py`:

Line 135: `MSMetricName.MS_POE_PORT_POWER_WATTS` -> `MSMetricName.MS_POE_PORT_POWER_WATTHOURS`
Line 152: `MSMetricName.MS_POE_TOTAL_POWER_WATTS` -> `MSMetricName.MS_POE_TOTAL_POWER_WATTHOURS`
Line 182: `MSMetricName.MS_POE_NETWORK_TOTAL_WATTS` -> `MSMetricName.MS_POE_NETWORK_TOTAL_WATTHOURS`

- [ ] **Step 5: Search for any other references**

Run: `uv run ruff check . && grep -r "MS_POE_PORT_POWER_WATTS\|MS_POE_TOTAL_POWER_WATTS\|MS_POE_NETWORK_TOTAL_WATTS" src/ tests/`
Expected: No matches (all old names replaced). If matches found, update them.

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_metrics_constants.py -v`
Expected: PASS

- [ ] **Step 7: Run existing MS collector tests**

Run: `uv run pytest tests/unit/collectors/test_ms_collector.py -v`
Expected: PASS (string values unchanged, only enum member names changed)

- [ ] **Step 8: Verify dashboard JSON uses string values (not enum names)**

The dashboard file `dashboards/ms-switches.json` references the Prometheus metric string names (`meraki_ms_poe_port_power_watthours`, etc.), NOT the Python enum names. Since the string values are unchanged, no dashboard updates are needed.

Run: `grep -c "meraki_ms_poe.*watthours" dashboards/ms-switches.json`
Expected: 6 matches (unchanged)

- [ ] **Step 9: Commit**

```bash
git add src/meraki_dashboard_exporter/core/constants/metrics_constants.py src/meraki_dashboard_exporter/collectors/devices/ms.py tests/unit/test_metrics_constants.py
git commit -m "fix: rename POE metric enums from WATTS to WATTHOURS

The enum member names said WATTS but the metric string values were
watthours. Renamed MS_POE_PORT_POWER_WATTS -> MS_POE_PORT_POWER_WATTHOURS
(and 2 similar). String values unchanged so Prometheus metric names and
Grafana dashboards are unaffected."
```

---

### Task 3: Fix Unbounded Caches

**Files:**
- Modify: `src/meraki_dashboard_exporter/collectors/device.py:56-107,141`
- Modify: `src/meraki_dashboard_exporter/collectors/devices/ms.py:28-40,312-326`
- Test: `tests/unit/test_cache_cleanup.py`

- [ ] **Step 1: Write tests for cache eviction**

Create `tests/unit/test_cache_cleanup.py`:

```python
"""Tests for bounded cache behavior in collectors."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestPacketMetricsCacheBounding:
    """Verify DeviceCollector._packet_metrics_cache is bounded."""

    def test_cache_evicts_stale_entries(self) -> None:
        """Entries not updated in a collection cycle should be evicted."""
        from meraki_dashboard_exporter.collectors.device import DeviceCollector

        # Create a minimal mock for DeviceCollector
        collector = MagicMock(spec=DeviceCollector)
        collector._packet_metrics_cache = {"old_key:serial=AAA": 42.0, "old_key:serial=BBB": 10.0}

        # Simulate marking active keys during collection
        active_keys = {"old_key:serial=AAA"}

        # Call the eviction method
        DeviceCollector._evict_stale_cache_entries(collector, active_keys)

        assert "old_key:serial=AAA" in collector._packet_metrics_cache
        assert "old_key:serial=BBB" not in collector._packet_metrics_cache

    def test_cache_empty_after_no_active_keys(self) -> None:
        """All entries evicted when no keys are active."""
        from meraki_dashboard_exporter.collectors.device import DeviceCollector

        collector = MagicMock(spec=DeviceCollector)
        collector._packet_metrics_cache = {"key1": 1.0, "key2": 2.0}

        DeviceCollector._evict_stale_cache_entries(collector, set())

        assert collector._packet_metrics_cache == {}


class TestMSCollectorCacheBounding:
    """Verify MSCollector timestamp caches are bounded."""

    def test_port_usage_cache_evicts_stale_serials(self) -> None:
        """Serials not seen in current cycle should be evicted."""
        from meraki_dashboard_exporter.collectors.devices.ms import MSCollector

        collector = MagicMock(spec=MSCollector)
        collector._last_port_usage = {"AAAA-BBBB-CCCC": 100.0, "DDDD-EEEE-FFFF": 200.0}
        collector._last_packet_stats = {"AAAA-BBBB-CCCC": 100.0, "DDDD-EEEE-FFFF": 200.0}

        active_serials = {"AAAA-BBBB-CCCC"}

        MSCollector._evict_stale_serials(collector, active_serials)

        assert "AAAA-BBBB-CCCC" in collector._last_port_usage
        assert "DDDD-EEEE-FFFF" not in collector._last_port_usage
        assert "AAAA-BBBB-CCCC" in collector._last_packet_stats
        assert "DDDD-EEEE-FFFF" not in collector._last_packet_stats
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_cache_cleanup.py -v`
Expected: FAIL - `_evict_stale_cache_entries` and `_evict_stale_serials` don't exist yet

- [ ] **Step 3: Add eviction method to DeviceCollector**

In `src/meraki_dashboard_exporter/collectors/device.py`, add after the `_set_packet_metric_value` method (after line 107):

```python
    def _evict_stale_cache_entries(self, active_keys: set[str]) -> None:
        """Remove cache entries not seen in the current collection cycle.

        Parameters
        ----------
        active_keys : set[str]
            Cache keys that were updated during the current cycle.

        """
        stale_keys = set(self._packet_metrics_cache.keys()) - active_keys
        for key in stale_keys:
            del self._packet_metrics_cache[key]
        if stale_keys:
            logger.debug(
                "Evicted stale packet metric cache entries",
                evicted_count=len(stale_keys),
                remaining_count=len(self._packet_metrics_cache),
            )
```

- [ ] **Step 4: Track active keys and call eviction in DeviceCollector._collect_impl**

In `src/meraki_dashboard_exporter/collectors/device.py`, find the `_collect_impl` method. At the end of the method (after all org processing completes), add:

```python
        # Evict stale cache entries not updated this cycle
        self._evict_stale_cache_entries(self._active_cache_keys)
        self._active_cache_keys = set()
```

At the start of `_collect_impl`, add:
```python
        self._active_cache_keys: set[str] = set()
```

In `_set_packet_metric_value`, after line 104 (`self._packet_metrics_cache[cache_key] = value`), add:
```python
            if hasattr(self, "_active_cache_keys"):
                self._active_cache_keys.add(cache_key)
```

- [ ] **Step 5: Add eviction method to MSCollector**

In `src/meraki_dashboard_exporter/collectors/devices/ms.py`, add a method after `__init__`:

```python
    def _evict_stale_serials(self, active_serials: set[str]) -> None:
        """Remove timestamp cache entries for serials not seen this cycle.

        Parameters
        ----------
        active_serials : set[str]
            Device serials that were processed during the current cycle.

        """
        for cache in (self._last_port_usage, self._last_packet_stats):
            stale = set(cache.keys()) - active_serials
            for key in stale:
                del cache[key]
```

- [ ] **Step 6: Call MSCollector eviction from its collect flow**

The MSCollector's `collect(device)` method is called per-device by the parent DeviceCollector. The eviction should happen after all devices are processed. Add tracking in `collect()`:

In the MSCollector `collect` method, at the top add:
```python
        serial = device.get("serial", "")
        if hasattr(self, "_active_serials"):
            self._active_serials.add(serial)
```

In the DeviceCollector, after all device collection completes for an org, call:
```python
        self.ms_collector._evict_stale_serials(
            getattr(self.ms_collector, "_active_serials", set())
        )
        self.ms_collector._active_serials = set()
```

Initialize `_active_serials` in MSCollector `__init__`:
```python
        self._active_serials: set[str] = set()
```

- [ ] **Step 7: Run the cache tests**

Run: `uv run pytest tests/unit/test_cache_cleanup.py -v`
Expected: PASS

- [ ] **Step 8: Run existing tests to verify no regressions**

Run: `uv run pytest tests/unit/collectors/test_ms_collector.py tests/ -v --timeout=60`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/meraki_dashboard_exporter/collectors/device.py src/meraki_dashboard_exporter/collectors/devices/ms.py tests/unit/test_cache_cleanup.py
git commit -m "fix: bound packet metric and MS collector caches

DeviceCollector._packet_metrics_cache and MSCollector._last_port_usage /
_last_packet_stats grew unbounded as new device serials were encountered.
Added per-cycle eviction: entries not updated during the current
collection cycle are removed, bounding memory to current device count."
```

---

### Task 4: Resolve Commented-Out _collect_api_metrics

**Files:**
- Modify: `src/meraki_dashboard_exporter/collectors/organization.py:299-331`
- Test: `tests/unit/test_organization_collector.py` (existing)

- [ ] **Step 1: Read the API usage collector to understand the failure mode**

Read `src/meraki_dashboard_exporter/collectors/organization_collectors/api_usage.py` to understand what `_collect_api_metrics` does. It calls `getOrganizationApiRequestsOverview` with a 1-hour timespan. This endpoint is known to be unreliable on some Meraki orgs (404 for orgs without API access or certain license types).

- [ ] **Step 2: Re-enable with error handling**

In `src/meraki_dashboard_exporter/collectors/organization.py`, change lines 299-301:

```python
# Before:
                # Collect various metrics sequentially
                # Skip API metrics for now - it's often problematic
                # await self._collect_api_metrics(org_id, org_name)

# After:
                # Collect various metrics sequentially
                await self._collect_api_metrics(org_id, org_name)
```

- [ ] **Step 3: Add error handling to the delegation method**

In `src/meraki_dashboard_exporter/collectors/organization.py`, wrap `_collect_api_metrics` with the error handling decorator. Change lines 319-330:

```python
# Before:
    async def _collect_api_metrics(self, org_id: str, org_name: str) -> None:
        """Collect API usage metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        await self.api_usage_collector.collect(org_id, org_name)

# After:
    @with_error_handling(
        operation="Collect API usage metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_api_metrics(self, org_id: str, org_name: str) -> None:
        """Collect API usage metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        await self.api_usage_collector.collect(org_id, org_name)
```

Ensure the imports at the top of `organization.py` include `ErrorCategory` and `with_error_handling` (check if already imported).

- [ ] **Step 4: Run existing organization collector tests**

Run: `uv run pytest tests/unit/test_organization_collector.py -v`
Expected: PASS (error handling decorator means failures are caught, not raised)

- [ ] **Step 5: Run linting**

Run: `uv run ruff check src/meraki_dashboard_exporter/collectors/organization.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add src/meraki_dashboard_exporter/collectors/organization.py
git commit -m "fix: re-enable API metrics collection with error handling

_collect_api_metrics was commented out because it was 'often problematic'.
Re-enabled with @with_error_handling(continue_on_error=True) so API
usage metrics are collected when available but failures don't break
other organization metric collection."
```

---

### Task 5: Create SubCollectorMixin

**Files:**
- Create: `src/meraki_dashboard_exporter/collectors/subcollector_mixin.py`
- Modify: `src/meraki_dashboard_exporter/collectors/organization_collectors/base.py`
- Modify: `src/meraki_dashboard_exporter/collectors/devices/base.py`
- Modify: `src/meraki_dashboard_exporter/collectors/network_health_collectors/base.py`
- Test: `tests/unit/test_subcollector_mixin.py`

- [ ] **Step 1: Write tests for the mixin**

Create `tests/unit/test_subcollector_mixin.py`:

```python
"""Tests for SubCollectorMixin delegation."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from meraki_dashboard_exporter.collectors.subcollector_mixin import SubCollectorMixin


class ConcreteSubCollector(SubCollectorMixin):
    """Concrete implementation for testing."""

    def __init__(self, parent: MagicMock) -> None:
        self.parent = parent
        self.api = parent.api
        self.settings = parent.settings


class TestSubCollectorMixin:
    """Test SubCollectorMixin delegation behavior."""

    def test_set_metric_value_delegates_to_parent(self) -> None:
        """_set_metric_value calls parent._set_metric_value."""
        parent = MagicMock()
        collector = ConcreteSubCollector(parent)

        collector._set_metric_value("_my_metric", {"org_id": "123"}, 42.0)

        parent._set_metric_value.assert_called_once_with("_my_metric", {"org_id": "123"}, 42.0)

    def test_set_metric_value_noop_when_parent_missing_method(self) -> None:
        """_set_metric_value is a no-op if parent lacks the method."""
        parent = MagicMock(spec=[])  # No methods
        collector = ConcreteSubCollector(parent)

        # Should not raise
        collector._set_metric_value("_my_metric", {"org_id": "123"}, 42.0)

    def test_track_api_call_delegates_to_parent(self) -> None:
        """_track_api_call calls parent._track_api_call."""
        parent = MagicMock()
        collector = ConcreteSubCollector(parent)

        collector._track_api_call("getOrganizationDevices")

        parent._track_api_call.assert_called_once_with("getOrganizationDevices")

    def test_track_api_call_noop_when_parent_missing_method(self) -> None:
        """_track_api_call is a no-op if parent lacks the method."""
        parent = MagicMock(spec=[])
        collector = ConcreteSubCollector(parent)

        # Should not raise
        collector._track_api_call("getOrganizationDevices")

    def test_update_api_sets_api_attribute(self) -> None:
        """update_api sets self.api to the new API instance."""
        parent = MagicMock()
        collector = ConcreteSubCollector(parent)

        new_api = MagicMock()
        collector.update_api(new_api)

        assert collector.api is new_api
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_subcollector_mixin.py -v`
Expected: FAIL - `subcollector_mixin` module doesn't exist

- [ ] **Step 3: Create the SubCollectorMixin**

Create `src/meraki_dashboard_exporter/collectors/subcollector_mixin.py`:

```python
"""Mixin providing common sub-collector delegation patterns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..core.logging import get_logger

if TYPE_CHECKING:
    from meraki import DashboardAPI

logger = get_logger(__name__)


class SubCollectorMixin:
    """Mixin for sub-collectors that delegate metrics to a parent collector.

    Provides consistent implementations of _set_metric_value, _track_api_call,
    and update_api so all sub-collector base classes share the same delegation
    logic instead of each implementing their own version.

    Requires the using class to have:
    - self.parent: The parent collector instance
    - self.api: The Meraki DashboardAPI instance

    """

    parent: Any
    api: DashboardAPI

    def _set_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Set a metric value by delegating to the parent collector.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute on the parent.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. If None, the metric will not be updated.

        """
        if hasattr(self.parent, "_set_metric_value"):
            self.parent._set_metric_value(metric_name, labels, value)

    def _track_api_call(self, method_name: str) -> None:
        """Track an API call by delegating to the parent collector.

        Parameters
        ----------
        method_name : str
            Name of the API method being called.

        """
        if hasattr(self.parent, "_track_api_call"):
            self.parent._track_api_call(method_name)

    def update_api(self, api: DashboardAPI) -> None:
        """Update the API client instance.

        Parameters
        ----------
        api : DashboardAPI
            New API client instance.

        """
        self.api = api
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_subcollector_mixin.py -v`
Expected: PASS

- [ ] **Step 5: Update BaseOrganizationCollector to use mixin**

In `src/meraki_dashboard_exporter/collectors/organization_collectors/base.py`, replace the entire file:

```python
"""Base organization collector with common functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.logging import get_logger
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from ...core.config import Settings
    from ...services.inventory import OrganizationInventory
    from ..organization import OrganizationCollector

logger = get_logger(__name__)


class BaseOrganizationCollector(SubCollectorMixin):
    """Base class for organization sub-collectors."""

    def __init__(self, parent: OrganizationCollector) -> None:
        """Initialize base organization collector.

        Parameters
        ----------
        parent : OrganizationCollector
            Parent OrganizationCollector instance that has metrics defined.

        """
        self.parent = parent
        self.api = parent.api
        self.settings: Settings = parent.settings
        self.inventory: OrganizationInventory | None = getattr(parent, "inventory", None)
```

- [ ] **Step 6: Update BaseNetworkHealthCollector to use mixin**

In `src/meraki_dashboard_exporter/collectors/network_health_collectors/base.py`, replace the entire file:

```python
"""Base network health collector with common functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.logging import get_logger
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from ...core.config import Settings
    from ..network_health import NetworkHealthCollector

logger = get_logger(__name__)


class BaseNetworkHealthCollector(SubCollectorMixin):
    """Base class for network health sub-collectors."""

    def __init__(self, parent: NetworkHealthCollector) -> None:
        """Initialize base network health collector.

        Parameters
        ----------
        parent : NetworkHealthCollector
            Parent NetworkHealthCollector instance that has metrics defined.

        """
        self.parent = parent
        self.api = parent.api
        self.settings: Settings = parent.settings
```

- [ ] **Step 7: Update BaseDeviceCollector to use mixin**

In `src/meraki_dashboard_exporter/collectors/devices/base.py`, change the class definition and remove the duplicate `_set_metric_value` and `_track_api_call` methods:

Change the imports at the top to add:
```python
from ..subcollector_mixin import SubCollectorMixin
```

Change the class declaration from:
```python
class BaseDeviceCollector(ABC):
```
to:
```python
class BaseDeviceCollector(SubCollectorMixin, ABC):
```

Remove the `_track_api_call` method (lines 79-89) - now inherited from mixin.

Remove the `_set_metric_value` method (lines 219-235) - now inherited from mixin.

- [ ] **Step 8: Run all existing tests**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: PASS (behavior unchanged, just consolidated)

- [ ] **Step 9: Run linting and type check**

Run: `uv run ruff check src/meraki_dashboard_exporter/collectors/ && uv run mypy src/meraki_dashboard_exporter/collectors/`
Expected: No errors

- [ ] **Step 10: Commit**

```bash
git add src/meraki_dashboard_exporter/collectors/subcollector_mixin.py src/meraki_dashboard_exporter/collectors/organization_collectors/base.py src/meraki_dashboard_exporter/collectors/devices/base.py src/meraki_dashboard_exporter/collectors/network_health_collectors/base.py tests/unit/test_subcollector_mixin.py
git commit -m "refactor: consolidate _set_metric_value into SubCollectorMixin

Previously 5 different implementations of _set_metric_value existed
across base classes. Created SubCollectorMixin with a single delegation
implementation. BaseOrganizationCollector, BaseDeviceCollector, and
BaseNetworkHealthCollector now inherit from the mixin instead of each
having their own copy."
```

---

### Task 6: Standardize Sub-Collector Initialization and API Updates

**Files:**
- Modify: `src/meraki_dashboard_exporter/collectors/device.py:143-144,191-204`
- Modify: `src/meraki_dashboard_exporter/collectors/devices/ms.py` (verify `_initialize_metrics` in `__init__`)
- Modify: `src/meraki_dashboard_exporter/collectors/devices/mr/collector.py` (update `update_api` to use mixin)

- [ ] **Step 1: Verify MSCollector initializes its own metrics**

Read `src/meraki_dashboard_exporter/collectors/devices/ms.py` `__init__` and check if `_initialize_metrics()` is called internally. Currently DeviceCollector calls `self.ms_collector._initialize_metrics()` at line 144. MSCollector should call it itself.

- [ ] **Step 2: Move _initialize_metrics call into MSCollector.__init__**

In `src/meraki_dashboard_exporter/collectors/devices/ms.py`, at the end of `__init__` (after line 40), add:
```python
        self._initialize_metrics()
```

In `src/meraki_dashboard_exporter/collectors/device.py`, remove line 144:
```python
# Remove this line:
        self.ms_collector._initialize_metrics()
```

- [ ] **Step 3: Standardize _sync_subcollector_api to use update_api**

In `src/meraki_dashboard_exporter/collectors/device.py`, replace `_sync_subcollector_api` (lines 191-204):

```python
# Before:
    def _sync_subcollector_api(self) -> None:
        """Ensure subcollectors use the current API client."""
        if hasattr(self, "mg_collector"):
            self.mg_collector.api = self.api
        if hasattr(self, "mr_collector"):
            self.mr_collector.update_api(self.api)
        if hasattr(self, "ms_collector"):
            self.ms_collector.api = self.api
        if hasattr(self, "mt_collector"):
            self.mt_collector.api = self.api
        if hasattr(self, "mv_collector"):
            self.mv_collector.api = self.api
        if hasattr(self, "mx_collector"):
            self.mx_collector.api = self.api

# After:
    def _sync_subcollector_api(self) -> None:
        """Ensure subcollectors use the current API client."""
        for collector in self._device_collectors.values():
            collector.update_api(self.api)
```

This works because all sub-collectors now inherit `update_api` from `SubCollectorMixin`.

- [ ] **Step 4: Update MRCollector.update_api to also propagate to its sub-collectors**

In `src/meraki_dashboard_exporter/collectors/devices/mr/collector.py`, the existing `update_api` method propagates to MR's own sub-collectors. Keep this method but have it call `super().update_api(api)` first:

```python
    def update_api(self, api: DashboardAPI) -> None:
        """Propagate API updates to sub-collectors."""
        super().update_api(api)
        self.clients.update_api(api)
        self.performance.update_api(api)
        self.wireless.update_api(api)
```

This requires MR sub-collectors (clients, performance, wireless) to also have `update_api`. Since they inherit from `BaseDeviceCollector` which now has `SubCollectorMixin`, they already have it.

- [ ] **Step 5: Run all tests**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/meraki_dashboard_exporter/collectors/device.py src/meraki_dashboard_exporter/collectors/devices/ms.py src/meraki_dashboard_exporter/collectors/devices/mr/collector.py
git commit -m "refactor: standardize sub-collector init and API updates

MSCollector now calls _initialize_metrics() in its own __init__ instead
of relying on DeviceCollector to call it externally. _sync_subcollector_api
now uses update_api() uniformly for all sub-collectors via SubCollectorMixin
instead of mixing direct attribute assignment with method calls."
```

---

### Task 7: Refactor MTCollector Dual Mode

**Files:**
- Modify: `src/meraki_dashboard_exporter/collectors/devices/mt.py:42-61`
- Modify: `src/meraki_dashboard_exporter/collectors/mt_sensor.py:47-53`
- Test: `tests/unit/test_mt_collector_factory.py`

- [ ] **Step 1: Write tests for the factory pattern**

Create `tests/unit/test_mt_collector_factory.py`:

```python
"""Tests for MTCollector factory methods."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.collectors.devices.mt import MTCollector


class TestMTCollectorFactory:
    """Test MTCollector creation modes."""

    def test_as_subcollector_sets_parent(self) -> None:
        """as_subcollector creates a collector with the given parent."""
        parent = MagicMock()
        parent.api = MagicMock()
        parent.settings = MagicMock()

        collector = MTCollector.as_subcollector(parent)

        assert collector.parent is parent
        assert collector.api is parent.api

    def test_as_standalone_has_no_parent(self) -> None:
        """as_standalone creates a collector without a parent."""
        api = MagicMock()
        settings = MagicMock()

        collector = MTCollector.as_standalone(api=api, settings=settings)

        assert collector.api is api
        assert collector.settings is settings

    def test_as_standalone_accepts_parent_reassignment(self) -> None:
        """Standalone collectors accept parent assignment for metric access."""
        api = MagicMock()
        settings = MagicMock()
        parent_proxy = MagicMock()

        collector = MTCollector.as_standalone(api=api, settings=settings)
        collector.parent = parent_proxy

        assert collector.parent is parent_proxy

    def test_no_type_ignore_in_standalone(self) -> None:
        """Standalone mode should not require type: ignore comments."""
        import ast
        from pathlib import Path

        source = Path("src/meraki_dashboard_exporter/collectors/devices/mt.py").read_text()

        # Verify no type: ignore[assignment] for parent or settings
        for i, line in enumerate(source.splitlines(), 1):
            if "self.parent = None" in line and "type: ignore" in line:
                pytest.fail(f"Line {i}: type: ignore still present on parent assignment")
            if "self.settings = None" in line and "type: ignore" in line:
                pytest.fail(f"Line {i}: type: ignore still present on settings assignment")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_mt_collector_factory.py -v`
Expected: FAIL - `as_subcollector` and `as_standalone` don't exist

- [ ] **Step 3: Refactor MTCollector.__init__ with factory methods**

In `src/meraki_dashboard_exporter/collectors/devices/mt.py`, replace the `__init__` method (lines 42-61):

```python
    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MT collector as a sub-collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance.

        """
        super().__init__(parent)

    @classmethod
    def as_subcollector(cls, parent: DeviceCollector) -> MTCollector:
        """Create as a sub-collector of DeviceCollector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance.

        Returns
        -------
        MTCollector
            Initialized sub-collector.

        """
        return cls(parent)

    @classmethod
    def as_standalone(
        cls,
        api: DashboardAPI,
        settings: Settings,
    ) -> MTCollector:
        """Create as an independent collector for MTSensorCollector.

        Parameters
        ----------
        api : DashboardAPI
            Meraki API client.
        settings : Settings
            Application settings.

        Returns
        -------
        MTCollector
            Initialized standalone collector.

        """
        instance = object.__new__(cls)
        instance.parent = None  # Will be reassigned by MTSensorCollector
        instance.api = api
        instance.settings = settings
        return instance
```

Add `Settings` to the TYPE_CHECKING imports:
```python
if TYPE_CHECKING:
    from ...core.config import Settings
    from ..device import DeviceCollector
```

Remove the `_standalone_mode` flag and all references to it throughout the file. Search for `_standalone_mode` and replace the checks:

```python
# Before (around line 492):
        if not self.parent and not getattr(self, "_standalone_mode", False):
            logger.error("Parent collector not set for MTCollector")
            return

# After:
        if not self.parent:
            logger.error("Parent collector not set for MTCollector")
            return
```

Also update `_track_api_call` (lines 63-76) - the standalone check is no longer needed since the parent check already handles it via the mixin.

- [ ] **Step 4: Update MTSensorCollector to use factory**

In `src/meraki_dashboard_exporter/collectors/mt_sensor.py`, change lines 47-53:

```python
# Before:
        # Create MT collector in standalone mode
        self.mt_collector = MTCollector(None)
        # Pass API and settings to MT collector
        self.mt_collector.api = api
        self.mt_collector.settings = settings
        # Pass this collector as the parent for metric access
        # This allows MTCollector to use MTSensorCollector's metrics
        self.mt_collector.parent = self  # type: ignore[assignment]

# After:
        # Create MT collector in standalone mode with factory method
        self.mt_collector = MTCollector.as_standalone(api=api, settings=settings)
        # Pass this collector as the parent for metric access
        self.mt_collector.parent = self  # type: ignore[assignment]
```

Note: The `type: ignore[assignment]` on the parent reassignment line remains because `self` is `MTSensorCollector` not `DeviceCollector`. This is a deliberate type widening, not a bug.

- [ ] **Step 5: Update DeviceCollector to use factory**

In `src/meraki_dashboard_exporter/collectors/device.py`, change line 126:

```python
# Before:
        self.mt_collector = MTCollector(self)
# After:
        self.mt_collector = MTCollector.as_subcollector(self)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/test_mt_collector_factory.py tests/ -v --timeout=60`
Expected: PASS

- [ ] **Step 7: Run linting and type check**

Run: `uv run ruff check src/meraki_dashboard_exporter/collectors/devices/mt.py src/meraki_dashboard_exporter/collectors/mt_sensor.py && uv run mypy src/meraki_dashboard_exporter/collectors/devices/mt.py src/meraki_dashboard_exporter/collectors/mt_sensor.py`
Expected: No errors (or fewer type: ignore comments than before)

- [ ] **Step 8: Commit**

```bash
git add src/meraki_dashboard_exporter/collectors/devices/mt.py src/meraki_dashboard_exporter/collectors/mt_sensor.py src/meraki_dashboard_exporter/collectors/device.py tests/unit/test_mt_collector_factory.py
git commit -m "refactor: replace MTCollector dual-mode with factory methods

MTCollector.__init__ previously used 'self.parent = None  # type: ignore'
and a _standalone_mode flag. Replaced with explicit factory methods:
- MTCollector.as_subcollector(parent) for DeviceCollector usage
- MTCollector.as_standalone(api, settings) for MTSensorCollector usage

Eliminates type: ignore hacks and conditional logic scattered through
the class."
```

---

### Task 8: Standardize Error Handling Conventions

**Files:**
- Modify: `src/meraki_dashboard_exporter/collectors/organization_collectors/license.py` (document the manual pattern)
- Modify: `src/meraki_dashboard_exporter/collectors/devices/ms.py` (migrate manual handlers where possible)
- Create: `src/meraki_dashboard_exporter/collectors/ERROR_HANDLING.md`

- [ ] **Step 1: Audit existing manual try/except patterns**

Search for manual `try/except` in collectors that should use the decorator:

Run: `grep -n "except Exception" src/meraki_dashboard_exporter/collectors/ -r`

Review each match. The convention is:
- `@with_error_handling()`: All API calls and collection methods
- Manual `try/except`: Only for specific recovery logic (e.g., 404 -> empty state)

- [ ] **Step 2: Document the convention**

Create `src/meraki_dashboard_exporter/collectors/ERROR_HANDLING.md`:

```markdown
# Error Handling Convention

## When to use `@with_error_handling()` decorator

- All methods that make API calls (directly or via `asyncio.to_thread`)
- All top-level `_collect_impl()` and `collect()` methods
- Parameters: `continue_on_error=True` for non-critical collectors, appropriate `ErrorCategory`

## When to use manual `try/except`

Only for specific recovery logic that cannot be expressed via decorator parameters:

- **404 fallback**: When an API returns 404 for a valid but empty state (e.g., org has no licenses)
- **Response format branching**: When different response shapes require different processing
- **Partial success**: When processing a batch where individual items can fail independently

In these cases, still use the decorator on the outer method and manual handling inside.

## Examples

### Decorator (standard):
```python
@with_error_handling(
    operation="Fetch devices",
    continue_on_error=True,
    error_category=ErrorCategory.API_CLIENT_ERROR,
)
async def _fetch_devices(self, org_id: str) -> list | None:
    ...
```

### Manual (404 recovery):
```python
@with_error_handling(operation="Collect licenses", continue_on_error=True)
async def collect(self, org_id: str, org_name: str) -> None:
    try:
        overview = await self._fetch_licenses(org_id)
        self._process(overview)
    except Exception as e:
        if "404" in str(e):
            logger.debug("No licensing info for org", org_id=org_id)
        else:
            raise  # Let decorator handle non-404 errors
```
```

- [ ] **Step 3: Add decorator to LicenseCollector.collect outer method**

In `src/meraki_dashboard_exporter/collectors/organization_collectors/license.py`, add the decorator to the `collect` method while keeping the internal 404 handling:

```python
    @with_error_handling(
        operation="Collect license metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str) -> None:
        """Collect license metrics."""
        try:
            # ... existing logic ...
        except Exception as e:
            if "404" in str(e):
                logger.debug("No licensing info available", org_id=org_id)
            else:
                raise  # Let decorator handle retries for non-404 errors
```

Add imports at the top of the file:
```python
from ...core.error_handling import ErrorCategory, with_error_handling
```

- [ ] **Step 4: Run existing tests**

Run: `uv run pytest tests/unit/test_license_collector.py tests/ -v --timeout=60`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/meraki_dashboard_exporter/collectors/ERROR_HANDLING.md src/meraki_dashboard_exporter/collectors/organization_collectors/license.py
git commit -m "refactor: standardize error handling conventions

Added ERROR_HANDLING.md documenting when to use @with_error_handling
decorator vs manual try/except. Added decorator to LicenseCollector
while preserving its 404 recovery logic inside a manual handler."
```

---

### Task 9: Move Port Overview Metrics to MSCollector

**Files:**
- Modify: `src/meraki_dashboard_exporter/collectors/device.py:146-185`
- Modify: `src/meraki_dashboard_exporter/collectors/devices/ms.py`
- Test: existing MS collector tests

- [ ] **Step 1: Identify where port overview metrics are SET**

Search for `_ms_ports_active_total`, `_ms_ports_inactive_total`, `_ms_ports_by_media_total`, `_ms_ports_by_link_speed_total` in the codebase to find where they're used during collection:

Run: `grep -rn "_ms_ports_" src/meraki_dashboard_exporter/collectors/`

These metrics are currently on `DeviceCollector` (self._ms_ports_*) and set via `self._ms_ports_active_total.labels(...).set(...)` somewhere in the collection flow. The references need to move to MSCollector.

- [ ] **Step 2: Move metric initialization to MSCollector._initialize_metrics**

In `src/meraki_dashboard_exporter/collectors/devices/ms.py`, add the port overview metrics at the end of `_initialize_metrics()`:

```python
        # Port overview metrics (org-level aggregates)
        self._ms_ports_active_total = self.parent._create_gauge(
            MSMetricName.MS_PORTS_ACTIVE_TOTAL,
            "Total number of active switch ports",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
            ],
        )

        self._ms_ports_inactive_total = self.parent._create_gauge(
            MSMetricName.MS_PORTS_INACTIVE_TOTAL,
            "Total number of inactive switch ports",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
            ],
        )

        self._ms_ports_by_media_total = self.parent._create_gauge(
            MSMetricName.MS_PORTS_BY_MEDIA_TOTAL,
            "Total number of switch ports by media type",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.MEDIA,
                LabelName.STATUS,
            ],
        )

        self._ms_ports_by_link_speed_total = self.parent._create_gauge(
            MSMetricName.MS_PORTS_BY_LINK_SPEED_TOTAL,
            "Total number of active switch ports by link speed",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.MEDIA,
                LabelName.LINK_SPEED,
            ],
        )
```

- [ ] **Step 3: Remove port overview metrics from DeviceCollector**

In `src/meraki_dashboard_exporter/collectors/device.py`, remove lines 146-185 (the four `_ms_ports_*` gauge initializations and the comment).

Replace with a comment:
```python
        # Port overview metrics are initialized in MSCollector._initialize_metrics()
```

- [ ] **Step 4: Update references in collection logic**

Search for all places in DeviceCollector that reference `self._ms_ports_*` and change them to `self.ms_collector._ms_ports_*`. If the collection logic for port overview is in DeviceCollector, move it to MSCollector or delegate:

Run: `grep -n "_ms_ports_" src/meraki_dashboard_exporter/collectors/device.py`

Update each reference to go through `self.ms_collector._ms_ports_*`.

- [ ] **Step 5: Run all tests**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: PASS

- [ ] **Step 6: Run linting and type check**

Run: `make check`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/meraki_dashboard_exporter/collectors/device.py src/meraki_dashboard_exporter/collectors/devices/ms.py
git commit -m "refactor: move port overview metrics from DeviceCollector to MSCollector

Port overview metrics (_ms_ports_active_total, _ms_ports_inactive_total,
_ms_ports_by_media_total, _ms_ports_by_link_speed_total) were initialized
in DeviceCollector but logically belong with MSCollector. Moved initialization
to MSCollector._initialize_metrics() so the coordinator only coordinates."
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
uv run pytest tests/ -v --timeout=120
```
Expected: All tests pass

- [ ] **Run full quality checks**

```bash
make check
```
Expected: Lint, typecheck, and tests all pass

- [ ] **Verify no regressions in metric output**

If possible, run the exporter briefly against a test environment and confirm `/metrics` output is unchanged (metric names, label sets, values should be identical except for the POE enum rename which doesn't affect string values).
