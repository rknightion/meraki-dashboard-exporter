# Status Health Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/status` endpoint that exposes exporter self-health as both HTML and JSON, aggregating collector status, API health, data freshness, and system info from existing internal managers.

**Architecture:** A `StatusService` in `services/status.py` reads state from `CollectorManager`, `MetricExpirationManager`, `OrgRateLimiter`, and `AsyncMerakiClient`, assembles a `StatusSnapshot` dataclass, and returns it. A new route in `app.py` serves the snapshot as HTML (default) or JSON (`?format=json`). A Jinja2 template renders the HTML view.

**Tech Stack:** Python 3.14, FastAPI, Jinja2, dataclasses, pytest, FastAPI TestClient

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/meraki_dashboard_exporter/services/status.py` | Create | `StatusSnapshot` dataclass, `CollectorStatus` dataclass, `ApiHealthStatus` dataclass, `DataFreshnessStatus` dataclass, `SystemStatus` dataclass, `OrgHealthStatus` dataclass, `StatusService` class |
| `src/meraki_dashboard_exporter/templates/status.html` | Create | Jinja2 HTML template for the browser view |
| `src/meraki_dashboard_exporter/app.py` | Modify (lines ~65, ~470, ~580) | Import `StatusService`, instantiate it in `__init__`, add `GET /status` route |
| `src/meraki_dashboard_exporter/templates/index.html` | Modify (lines ~544-552) | Add `/status` link in the endpoint list |
| `tests/unit/test_status_service.py` | Create | Unit tests for `StatusService` and snapshot logic |
| `tests/unit/test_status_endpoint.py` | Create | Integration tests for `/status` route (HTML + JSON) |

---

### Task 1: StatusSnapshot Dataclasses

**Files:**
- Create: `tests/unit/test_status_service.py`
- Create: `src/meraki_dashboard_exporter/services/status.py`

- [ ] **Step 1: Write failing test for dataclass construction**

```python
"""Tests for the StatusService and StatusSnapshot."""

from __future__ import annotations

from meraki_dashboard_exporter.services.status import (
    ApiHealthStatus,
    CollectorStatus,
    DataFreshnessStatus,
    OrgHealthStatus,
    StatusSnapshot,
    SystemStatus,
)


class TestStatusSnapshot:
    """Tests for StatusSnapshot dataclass construction."""

    def test_snapshot_round_trips_to_dict(self) -> None:
        """A snapshot can be converted to a dict for JSON serialization."""
        snapshot = StatusSnapshot(
            timestamp="2026-04-14T12:00:00Z",
            system=SystemStatus(
                version="1.0.0",
                uptime="3h 42m",
                readiness={"ready": True, "collectors": {"fast": True, "medium": True, "slow": True}},
                org_health=[],
            ),
            collectors=[
                CollectorStatus(
                    name="DeviceCollector",
                    tier="FAST",
                    total_runs=10,
                    total_successes=9,
                    total_failures=1,
                    success_rate=90.0,
                    failure_streak=0,
                    last_success_time=1744632000.0,
                    last_success_ago="30s ago",
                    is_running=False,
                    staleness="ok",
                ),
            ],
            api_health=ApiHealthStatus(
                total_calls=100,
                throttle_events=2,
                per_org_rate_limits=[{"org_id": "123", "tokens_remaining": 5.0}],
            ),
            data_freshness=DataFreshnessStatus(
                total_tracked_metrics=500,
                by_collector={"DeviceCollector": 200},
                ttl_multiplier=2.0,
            ),
        )

        result = snapshot.to_dict()

        assert result["timestamp"] == "2026-04-14T12:00:00Z"
        assert result["system"]["version"] == "1.0.0"
        assert result["collectors"][0]["name"] == "DeviceCollector"
        assert result["collectors"][0]["success_rate"] == 90.0
        assert result["api_health"]["total_calls"] == 100
        assert result["data_freshness"]["total_tracked_metrics"] == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_status_service.py::TestStatusSnapshot::test_snapshot_round_trips_to_dict -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'meraki_dashboard_exporter.services.status'`

- [ ] **Step 3: Implement the dataclasses**

Create `src/meraki_dashboard_exporter/services/status.py`:

```python
"""Exporter self-health status service."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..api.client import AsyncMerakiClient
    from ..collectors.manager import CollectorManager
    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager


@dataclass
class CollectorStatus:
    """Health status for a single collector."""

    name: str
    tier: str
    total_runs: int
    total_successes: int
    total_failures: int
    success_rate: float
    failure_streak: int
    last_success_time: float | None
    last_success_ago: str
    is_running: bool
    staleness: str


@dataclass
class ApiHealthStatus:
    """API client health summary."""

    total_calls: int
    throttle_events: int
    per_org_rate_limits: list[dict[str, Any]]


@dataclass
class DataFreshnessStatus:
    """Metric freshness summary."""

    total_tracked_metrics: int
    by_collector: dict[str, int]
    ttl_multiplier: float


@dataclass
class OrgHealthStatus:
    """Per-organization health state."""

    org_id: str
    org_name: str
    consecutive_failures: int
    in_backoff: bool
    backoff_remaining_seconds: float


@dataclass
class SystemStatus:
    """System-level status info."""

    version: str
    uptime: str
    readiness: dict[str, Any]
    org_health: list[OrgHealthStatus | dict[str, Any]]


@dataclass
class StatusSnapshot:
    """Point-in-time snapshot of exporter health."""

    timestamp: str
    system: SystemStatus
    collectors: list[CollectorStatus]
    api_health: ApiHealthStatus
    data_freshness: DataFreshnessStatus

    def to_dict(self) -> dict[str, Any]:
        """Serialize the snapshot to a plain dict for JSON output."""
        return asdict(self)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_status_service.py::TestStatusSnapshot::test_snapshot_round_trips_to_dict -v`
Expected: PASS

- [ ] **Step 5: Commit**

```
git add tests/unit/test_status_service.py src/meraki_dashboard_exporter/services/status.py
git commit -m "feat(status): add StatusSnapshot dataclasses with serialization"
```

---

### Task 2: Staleness Computation Logic

**Files:**
- Modify: `tests/unit/test_status_service.py`
- Modify: `src/meraki_dashboard_exporter/services/status.py`

- [ ] **Step 1: Write failing tests for staleness and time-ago helpers**

Append to `tests/unit/test_status_service.py`:

```python
from meraki_dashboard_exporter.services.status import (
    _compute_staleness,
    _format_time_ago,
)


class TestStalenessComputation:
    """Tests for staleness threshold logic."""

    def test_ok_when_within_one_interval(self) -> None:
        """Staleness is 'ok' when last success is within 1x the tier interval."""
        now = 1000.0
        last_success = 950.0  # 50s ago
        interval = 60  # FAST tier
        assert _compute_staleness(last_success, interval, now) == "ok"

    def test_warning_when_between_one_and_two_intervals(self) -> None:
        """Staleness is 'warning' between 1x and 2x the tier interval."""
        now = 1000.0
        last_success = 920.0  # 80s ago
        interval = 60  # FAST tier, so 1x=60, 2x=120
        assert _compute_staleness(last_success, interval, now) == "warning"

    def test_stale_when_beyond_two_intervals(self) -> None:
        """Staleness is 'stale' beyond 2x the tier interval."""
        now = 1000.0
        last_success = 800.0  # 200s ago
        interval = 60  # 2x=120, 200 > 120
        assert _compute_staleness(last_success, interval, now) == "stale"

    def test_stale_when_never_succeeded(self) -> None:
        """Staleness is 'stale' when last_success_time is None."""
        assert _compute_staleness(None, 60, 1000.0) == "stale"

    def test_ok_at_exact_boundary(self) -> None:
        """Staleness is 'ok' when exactly at 1x the interval (not exceeded)."""
        now = 1000.0
        last_success = 940.0  # exactly 60s ago
        assert _compute_staleness(last_success, 60, now) == "ok"

    def test_warning_at_exact_two_x_boundary(self) -> None:
        """Staleness is 'warning' when exactly at 2x (not exceeded)."""
        now = 1000.0
        last_success = 880.0  # exactly 120s ago
        assert _compute_staleness(last_success, 60, now) == "warning"


class TestFormatTimeAgo:
    """Tests for human-readable relative time formatting."""

    def test_seconds_ago(self) -> None:
        assert _format_time_ago(950.0, 1000.0) == "50s ago"

    def test_minutes_ago(self) -> None:
        assert _format_time_ago(700.0, 1000.0) == "5m ago"

    def test_hours_ago(self) -> None:
        assert _format_time_ago(0.0, 7200.0) == "2h ago"

    def test_none_returns_never(self) -> None:
        assert _format_time_ago(None, 1000.0) == "Never"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_status_service.py::TestStalenessComputation -v && uv run pytest tests/unit/test_status_service.py::TestFormatTimeAgo -v`
Expected: FAIL with `ImportError: cannot import name '_compute_staleness'`

- [ ] **Step 3: Implement the helper functions**

Add to `src/meraki_dashboard_exporter/services/status.py`, above the dataclass definitions:

```python
def _compute_staleness(
    last_success_time: float | None,
    tier_interval: int,
    now: float | None = None,
) -> str:
    """Compute staleness category based on time since last success.

    Parameters
    ----------
    last_success_time : float | None
        Unix timestamp of last successful collection, or None if never succeeded.
    tier_interval : int
        The collection interval for this tier in seconds.
    now : float | None
        Current time as unix timestamp. Defaults to time.time().

    Returns
    -------
    str
        "ok", "warning", or "stale".

    """
    if last_success_time is None:
        return "stale"
    if now is None:
        now = time.time()
    age = now - last_success_time
    if age <= tier_interval:
        return "ok"
    if age <= tier_interval * 2:
        return "warning"
    return "stale"


def _format_time_ago(timestamp: float | None, now: float | None = None) -> str:
    """Format a unix timestamp as a human-readable relative time.

    Parameters
    ----------
    timestamp : float | None
        Unix timestamp, or None.
    now : float | None
        Current time as unix timestamp. Defaults to time.time().

    Returns
    -------
    str
        Human-readable string like "30s ago", "5m ago", "2h ago", or "Never".

    """
    if timestamp is None:
        return "Never"
    if now is None:
        now = time.time()
    age = int(now - timestamp)
    if age < 60:
        return f"{age}s ago"
    if age < 3600:
        return f"{age // 60}m ago"
    return f"{age // 3600}h ago"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_status_service.py::TestStalenessComputation tests/unit/test_status_service.py::TestFormatTimeAgo -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```
git add tests/unit/test_status_service.py src/meraki_dashboard_exporter/services/status.py
git commit -m "feat(status): add staleness computation and time-ago formatting helpers"
```

---

### Task 3: StatusService.get_snapshot()

**Files:**
- Modify: `tests/unit/test_status_service.py`
- Modify: `src/meraki_dashboard_exporter/services/status.py`

- [ ] **Step 1: Write failing test for get_snapshot()**

Append to `tests/unit/test_status_service.py`:

```python
from unittest.mock import MagicMock, patch

from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.org_health import OrgHealth
from meraki_dashboard_exporter.services.status import StatusService


class TestStatusService:
    """Tests for StatusService.get_snapshot()."""

    def _make_service(self) -> tuple[StatusService, MagicMock, MagicMock, MagicMock, MagicMock]:
        """Create a StatusService with mock dependencies."""
        mock_manager = MagicMock()
        mock_expiration = MagicMock()
        mock_client = MagicMock()
        mock_settings = MagicMock()

        # Configure tier intervals
        mock_settings.update_intervals.fast = 60
        mock_settings.update_intervals.medium = 300
        mock_settings.update_intervals.slow = 900

        service = StatusService(
            collector_manager=mock_manager,
            expiration_manager=mock_expiration,
            client=mock_client,
            settings=mock_settings,
            start_time=0.0,
        )
        return service, mock_manager, mock_expiration, mock_client, mock_settings

    def test_get_snapshot_returns_snapshot(self) -> None:
        """get_snapshot() returns a StatusSnapshot with all sections populated."""
        service, mock_manager, mock_expiration, mock_client, _ = self._make_service()

        # Setup collector manager mocks
        mock_collector = MagicMock()
        mock_collector.__class__.__name__ = "DeviceCollector"
        mock_collector.is_active = True

        mock_manager.collectors = {
            UpdateTier.FAST: [mock_collector],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        mock_manager.collector_health = {
            "DeviceCollector": {
                "total_runs": 10,
                "total_successes": 9,
                "total_failures": 1,
                "failure_streak": 0,
                "last_success_time": 950.0,
            },
        }
        mock_manager.is_collector_running.return_value = False
        mock_manager.get_readiness_status.return_value = {
            "ready": True,
            "collectors": {"fast": True, "medium": True, "slow": True},
        }
        mock_manager.org_health_tracker._orgs = {}
        mock_manager.rate_limiter._tokens = {"123": 5.0}
        mock_manager.rate_limiter.enabled = True

        # Setup API client mock
        mock_client._api_call_count = 42

        # Setup expiration manager mock
        mock_expiration.get_stats.return_value = {
            "total_tracked": 500,
            "by_collector": {"DeviceCollector": 200},
            "ttl_multiplier": 2.0,
        }

        with patch("meraki_dashboard_exporter.services.status.time") as mock_time:
            mock_time.time.return_value = 1000.0

            snapshot = service.get_snapshot()

        assert snapshot.timestamp is not None
        assert snapshot.system.version is not None
        assert len(snapshot.collectors) == 1
        assert snapshot.collectors[0].name == "DeviceCollector"
        assert snapshot.collectors[0].tier == "FAST"
        assert snapshot.collectors[0].success_rate == 90.0
        assert snapshot.collectors[0].staleness == "ok"
        assert snapshot.collectors[0].last_success_ago == "50s ago"
        assert snapshot.api_health.total_calls == 42
        assert snapshot.api_health.per_org_rate_limits == [{"org_id": "123", "tokens_remaining": 5.0}]
        assert snapshot.data_freshness.total_tracked_metrics == 500

    def test_get_snapshot_handles_zero_runs(self) -> None:
        """get_snapshot() handles collectors with zero runs (avoids division by zero)."""
        service, mock_manager, mock_expiration, mock_client, _ = self._make_service()

        mock_collector = MagicMock()
        mock_collector.__class__.__name__ = "AlertCollector"
        mock_collector.is_active = True

        mock_manager.collectors = {
            UpdateTier.FAST: [mock_collector],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        mock_manager.collector_health = {
            "AlertCollector": {
                "total_runs": 0,
                "total_successes": 0,
                "total_failures": 0,
                "failure_streak": 0,
                "last_success_time": None,
            },
        }
        mock_manager.is_collector_running.return_value = False
        mock_manager.get_readiness_status.return_value = {
            "ready": False,
            "collectors": {"fast": False, "medium": False, "slow": False},
        }
        mock_manager.org_health_tracker._orgs = {}
        mock_manager.rate_limiter._tokens = {}
        mock_manager.rate_limiter.enabled = True
        mock_client._api_call_count = 0
        mock_expiration.get_stats.return_value = {
            "total_tracked": 0,
            "by_collector": {},
            "ttl_multiplier": 2.0,
        }

        with patch("meraki_dashboard_exporter.services.status.time") as mock_time:
            mock_time.time.return_value = 1000.0

            snapshot = service.get_snapshot()

        assert snapshot.collectors[0].success_rate == 0.0
        assert snapshot.collectors[0].staleness == "stale"

    def test_get_snapshot_includes_org_health_in_backoff(self) -> None:
        """get_snapshot() includes org health entries with backoff info."""
        service, mock_manager, mock_expiration, mock_client, _ = self._make_service()

        mock_manager.collectors = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        mock_manager.collector_health = {}
        mock_manager.get_readiness_status.return_value = {
            "ready": True,
            "collectors": {"fast": True, "medium": True, "slow": True},
        }
        mock_manager.org_health_tracker._orgs = {
            "org1": OrgHealth(
                org_id="org1",
                org_name="Acme Corp",
                consecutive_failures=5,
                last_failure=980.0,
                backoff_until=1060.0,
            ),
        }
        mock_manager.rate_limiter._tokens = {}
        mock_manager.rate_limiter.enabled = True
        mock_client._api_call_count = 0
        mock_expiration.get_stats.return_value = {
            "total_tracked": 0,
            "by_collector": {},
            "ttl_multiplier": 2.0,
        }

        with patch("meraki_dashboard_exporter.services.status.time") as mock_time:
            mock_time.time.return_value = 1000.0

            snapshot = service.get_snapshot()

        assert len(snapshot.system.org_health) == 1
        org = snapshot.system.org_health[0]
        assert org.org_id == "org1"
        assert org.org_name == "Acme Corp"
        assert org.in_backoff is True
        assert org.backoff_remaining_seconds == 60.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_status_service.py::TestStatusService -v`
Expected: FAIL with `ImportError: cannot import name 'StatusService'`

- [ ] **Step 3: Implement StatusService**

Add to `src/meraki_dashboard_exporter/services/status.py`, after the dataclass definitions:

```python
class StatusService:
    """Aggregates exporter self-health into a StatusSnapshot.

    Parameters
    ----------
    collector_manager : CollectorManager
        The collector manager instance.
    expiration_manager : MetricExpirationManager
        The metric expiration manager.
    client : AsyncMerakiClient
        The Meraki API client.
    settings : Settings
        Application settings.
    start_time : float
        Unix timestamp of application start.

    """

    def __init__(
        self,
        collector_manager: CollectorManager,
        expiration_manager: MetricExpirationManager,
        client: AsyncMerakiClient,
        settings: Settings,
        start_time: float,
    ) -> None:
        """Initialize the status service with references to existing managers."""
        self._manager = collector_manager
        self._expiration = expiration_manager
        self._client = client
        self._settings = settings
        self._start_time = start_time

    def get_snapshot(self) -> StatusSnapshot:
        """Build a point-in-time snapshot of exporter health.

        Returns
        -------
        StatusSnapshot
            The current health snapshot.

        """
        now = time.time()

        # Map tier enum -> interval for staleness computation
        tier_intervals = {
            UpdateTier.FAST: self._settings.update_intervals.fast,
            UpdateTier.MEDIUM: self._settings.update_intervals.medium,
            UpdateTier.SLOW: self._settings.update_intervals.slow,
        }

        # Build collector statuses
        collectors: list[CollectorStatus] = []
        for tier, collector_list in self._manager.collectors.items():
            interval = tier_intervals[tier]
            for collector in collector_list:
                if not collector.is_active:
                    continue
                name = collector.__class__.__name__
                health = self._manager.collector_health.get(name, {})
                total_runs = health.get("total_runs", 0)
                total_successes = health.get("total_successes", 0)
                total_failures = health.get("total_failures", 0)
                success_rate = (total_successes / total_runs * 100) if total_runs > 0 else 0.0
                last_success_time = health.get("last_success_time")

                collectors.append(
                    CollectorStatus(
                        name=name,
                        tier=tier.value.upper(),
                        total_runs=total_runs,
                        total_successes=total_successes,
                        total_failures=total_failures,
                        success_rate=round(success_rate, 1),
                        failure_streak=health.get("failure_streak", 0),
                        last_success_time=last_success_time,
                        last_success_ago=_format_time_ago(last_success_time, now),
                        is_running=self._manager.is_collector_running(name),
                        staleness=_compute_staleness(last_success_time, interval, now),
                    )
                )

        # Build API health
        rate_limiter = self._manager.rate_limiter
        per_org: list[dict[str, Any]] = []
        if rate_limiter.enabled:
            for org_id, tokens in rate_limiter._tokens.items():
                per_org.append({"org_id": org_id, "tokens_remaining": round(tokens, 1)})

        api_health = ApiHealthStatus(
            total_calls=self._client._api_call_count,
            throttle_events=0,  # Counter value not trivially readable; leave as 0 for now
            per_org_rate_limits=per_org,
        )

        # Build data freshness
        stats = self._expiration.get_stats()
        data_freshness = DataFreshnessStatus(
            total_tracked_metrics=stats["total_tracked"],
            by_collector=stats["by_collector"],
            ttl_multiplier=stats["ttl_multiplier"],
        )

        # Build org health
        org_health_list: list[OrgHealthStatus] = []
        for org_id, health in self._manager.org_health_tracker._orgs.items():
            remaining = max(0.0, health.backoff_until - now)
            org_health_list.append(
                OrgHealthStatus(
                    org_id=health.org_id,
                    org_name=health.org_name,
                    consecutive_failures=health.consecutive_failures,
                    in_backoff=remaining > 0,
                    backoff_remaining_seconds=round(remaining, 1),
                )
            )

        # Build uptime string
        uptime_seconds = int(now - self._start_time)
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        if days > 0:
            uptime = f"{days}d {hours}h"
        elif hours > 0:
            uptime = f"{hours}h {minutes}m"
        else:
            uptime = f"{minutes}m"

        # Import version lazily to avoid circular imports
        from ..__version__ import __version__

        system = SystemStatus(
            version=__version__,
            uptime=uptime,
            readiness=self._manager.get_readiness_status(),
            org_health=org_health_list,
        )

        return StatusSnapshot(
            timestamp=datetime.now(UTC).isoformat(),
            system=system,
            collectors=collectors,
            api_health=api_health,
            data_freshness=data_freshness,
        )
```

Also add this import at the top of the file (it's already in the TYPE_CHECKING block but needed at runtime now):

```python
from ..core.constants import UpdateTier
```

Move it outside the `TYPE_CHECKING` block since `get_snapshot()` uses `UpdateTier` at runtime.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_status_service.py::TestStatusService -v`
Expected: All PASS

- [ ] **Step 5: Run linting and type checks**

Run: `uv run ruff check src/meraki_dashboard_exporter/services/status.py tests/unit/test_status_service.py && uv run ruff format src/meraki_dashboard_exporter/services/status.py tests/unit/test_status_service.py`
Expected: Clean or auto-fixed

- [ ] **Step 6: Commit**

```
git add src/meraki_dashboard_exporter/services/status.py tests/unit/test_status_service.py
git commit -m "feat(status): implement StatusService.get_snapshot() with full health aggregation"
```

---

### Task 4: HTML Template

**Files:**
- Create: `src/meraki_dashboard_exporter/templates/status.html`

- [ ] **Step 1: Create the status template**

Create `src/meraki_dashboard_exporter/templates/status.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Exporter Status</title>
    <style>
        :root {
            --bg-color: #f5f5f5;
            --card-bg: #ffffff;
            --text-primary: #333333;
            --text-secondary: #666666;
            --success-color: #4caf50;
            --warning-color: #ff9800;
            --error-color: #f44336;
            --info-color: #2196f3;
            --border-color: #e0e0e0;
            --link-color: #1976d2;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 20px;
        }

        .container { max-width: 1200px; margin: 0 auto; }

        .header {
            background-color: var(--card-bg);
            border-radius: 8px;
            padding: 24px 30px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .header h1 { font-size: 1.8rem; }
        .header-meta { text-align: right; color: var(--text-secondary); font-size: 0.9rem; }

        .readiness-banner {
            border-radius: 8px;
            padding: 12px 20px;
            margin-bottom: 20px;
            font-weight: 600;
            display: flex;
            gap: 16px;
            align-items: center;
        }
        .readiness-ready { background-color: #e8f5e9; color: #2e7d32; }
        .readiness-not-ready { background-color: #fff3e0; color: #e65100; }
        .tier-pill {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .tier-complete { background-color: #c8e6c9; color: #2e7d32; }
        .tier-pending { background-color: #ffe0b2; color: #e65100; }

        .card {
            background-color: var(--card-bg);
            border-radius: 8px;
            padding: 20px 24px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .card h2 { font-size: 1.2rem; margin-bottom: 12px; }

        table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
        th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border-color); color: var(--text-secondary); font-weight: 600; }
        td { padding: 8px 10px; border-bottom: 1px solid var(--border-color); }

        .row-ok { }
        .row-warning { background-color: #fff8e1; }
        .row-stale { background-color: #ffebee; }

        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .badge-ok { background-color: #e8f5e9; color: #2e7d32; }
        .badge-warning { background-color: #fff3e0; color: #e65100; }
        .badge-stale { background-color: #ffebee; color: #c62828; }
        .badge-running { background-color: #e3f2fd; color: #1565c0; }

        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
        }
        .stat-item { padding: 8px 0; }
        .stat-value { font-size: 1.4rem; font-weight: 700; }
        .stat-label { font-size: 0.85rem; color: var(--text-secondary); }

        .nav-link {
            color: var(--link-color);
            text-decoration: none;
            font-size: 0.9rem;
        }
        .nav-link:hover { text-decoration: underline; }

        .collector-breakdown { margin-top: 8px; }
        .collector-breakdown dt { font-weight: 600; display: inline; }
        .collector-breakdown dd { display: inline; margin-left: 4px; margin-right: 16px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>Exporter Status</h1>
                <a href="/" class="nav-link">Back to home</a>
            </div>
            <div class="header-meta">
                <div>v{{ system.version }}</div>
                <div>Uptime: {{ system.uptime }}</div>
            </div>
        </div>

        <div class="readiness-banner {{ 'readiness-ready' if system.readiness.ready else 'readiness-not-ready' }}">
            <span>{{ 'Ready' if system.readiness.ready else 'Not Ready' }}</span>
            <span class="tier-pill {{ 'tier-complete' if system.readiness.collectors.fast else 'tier-pending' }}">FAST {{ 'done' if system.readiness.collectors.fast else 'pending' }}</span>
            <span class="tier-pill {{ 'tier-complete' if system.readiness.collectors.medium else 'tier-pending' }}">MEDIUM {{ 'done' if system.readiness.collectors.medium else 'pending' }}</span>
            <span class="tier-pill {{ 'tier-complete' if system.readiness.collectors.slow else 'tier-pending' }}">SLOW {{ 'done' if system.readiness.collectors.slow else 'pending' }}</span>
        </div>

        <div class="card">
            <h2>Collectors ({{ collectors | length }})</h2>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Tier</th>
                        <th>Runs</th>
                        <th>Success Rate</th>
                        <th>Failure Streak</th>
                        <th>Last Success</th>
                        <th>Staleness</th>
                        <th>Running</th>
                    </tr>
                </thead>
                <tbody>
                    {% for c in collectors %}
                    <tr class="{{ 'row-stale' if c.staleness == 'stale' or c.failure_streak >= 3 else 'row-warning' if c.staleness == 'warning' else 'row-ok' }}">
                        <td>{{ c.name }}</td>
                        <td>{{ c.tier }}</td>
                        <td>{{ c.total_runs }}</td>
                        <td>{{ "%.1f"|format(c.success_rate) }}%</td>
                        <td>{{ c.failure_streak }}</td>
                        <td>{{ c.last_success_ago }}</td>
                        <td><span class="badge badge-{{ c.staleness }}">{{ c.staleness }}</span></td>
                        <td>{% if c.is_running %}<span class="badge badge-running">yes</span>{% else %}no{% endif %}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>API Health</h2>
            <div class="stat-grid">
                <div class="stat-item">
                    <div class="stat-value">{{ api_health.total_calls }}</div>
                    <div class="stat-label">Total API Calls</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{{ api_health.throttle_events }}</div>
                    <div class="stat-label">Throttle Events</div>
                </div>
            </div>
            {% if api_health.per_org_rate_limits %}
            <table style="margin-top: 12px;">
                <thead><tr><th>Org ID</th><th>Tokens Remaining</th></tr></thead>
                <tbody>
                    {% for entry in api_health.per_org_rate_limits %}
                    <tr><td>{{ entry.org_id }}</td><td>{{ entry.tokens_remaining }}</td></tr>
                    {% endfor %}
                </tbody>
            </table>
            {% endif %}
        </div>

        <div class="card">
            <h2>Data Freshness</h2>
            <div class="stat-grid">
                <div class="stat-item">
                    <div class="stat-value">{{ data_freshness.total_tracked_metrics }}</div>
                    <div class="stat-label">Tracked Metrics</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{{ data_freshness.ttl_multiplier }}x</div>
                    <div class="stat-label">TTL Multiplier</div>
                </div>
            </div>
            {% if data_freshness.by_collector %}
            <dl class="collector-breakdown">
                {% for name, count in data_freshness.by_collector.items() %}
                <dt>{{ name }}:</dt><dd>{{ count }}</dd>
                {% endfor %}
            </dl>
            {% endif %}
        </div>

        {% if system.org_health %}
        <div class="card">
            <h2>Organization Health</h2>
            <table>
                <thead><tr><th>Organization</th><th>Failures</th><th>In Backoff</th><th>Backoff Remaining</th></tr></thead>
                <tbody>
                    {% for org in system.org_health %}
                    <tr class="{{ 'row-stale' if org.in_backoff else '' }}">
                        <td>{{ org.org_name }} ({{ org.org_id }})</td>
                        <td>{{ org.consecutive_failures }}</td>
                        <td>{% if org.in_backoff %}<span class="badge badge-stale">yes</span>{% else %}no{% endif %}</td>
                        <td>{% if org.in_backoff %}{{ org.backoff_remaining_seconds }}s{% else %}-{% endif %}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
    </div>
</body>
</html>
```

- [ ] **Step 2: Verify the template file exists and is valid HTML**

Run: `python3 -c "from pathlib import Path; p = Path('src/meraki_dashboard_exporter/templates/status.html'); assert p.exists(); assert '<html' in p.read_text(); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```
git add src/meraki_dashboard_exporter/templates/status.html
git commit -m "feat(status): add status.html Jinja2 template"
```

---

### Task 5: Wire Up /status Route in app.py

**Files:**
- Create: `tests/unit/test_status_endpoint.py`
- Modify: `src/meraki_dashboard_exporter/app.py`

- [ ] **Step 1: Write failing tests for the /status endpoint**

Create `tests/unit/test_status_endpoint.py`:

```python
"""Tests for the /status endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.services.status import StatusSnapshot, SystemStatus, ApiHealthStatus, DataFreshnessStatus, CollectorStatus


@pytest.fixture
def test_settings() -> Settings:
    """Create minimal settings for endpoint testing."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )


@pytest.fixture
def app_client(test_settings: Settings) -> TestClient:
    """Create a TestClient for the FastAPI app."""
    exporter = ExporterApp(test_settings)
    fastapi_app = exporter.create_app()
    return TestClient(fastapi_app, raise_server_exceptions=True)


def _make_snapshot() -> StatusSnapshot:
    """Build a minimal StatusSnapshot for testing."""
    return StatusSnapshot(
        timestamp="2026-04-14T12:00:00Z",
        system=SystemStatus(
            version="1.0.0",
            uptime="1h 30m",
            readiness={"ready": True, "collectors": {"fast": True, "medium": True, "slow": True}},
            org_health=[],
        ),
        collectors=[
            CollectorStatus(
                name="DeviceCollector",
                tier="FAST",
                total_runs=10,
                total_successes=9,
                total_failures=1,
                success_rate=90.0,
                failure_streak=0,
                last_success_time=1000.0,
                last_success_ago="30s ago",
                is_running=False,
                staleness="ok",
            ),
        ],
        api_health=ApiHealthStatus(total_calls=42, throttle_events=0, per_org_rate_limits=[]),
        data_freshness=DataFreshnessStatus(total_tracked_metrics=500, by_collector={}, ttl_multiplier=2.0),
    )


class TestStatusEndpointHTML:
    """Tests for GET /status returning HTML."""

    def test_status_returns_html_by_default(self, app_client: TestClient) -> None:
        """GET /status returns an HTML page by default."""
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=_make_snapshot(),
        ):
            response = app_client.get("/status")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Exporter Status" in response.text
        assert "DeviceCollector" in response.text

    def test_status_html_contains_sections(self, app_client: TestClient) -> None:
        """The HTML page contains all expected sections."""
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=_make_snapshot(),
        ):
            response = app_client.get("/status")

        body = response.text
        assert "Collectors" in body
        assert "API Health" in body
        assert "Data Freshness" in body


class TestStatusEndpointJSON:
    """Tests for GET /status?format=json returning JSON."""

    def test_status_returns_json_when_requested(self, app_client: TestClient) -> None:
        """GET /status?format=json returns a JSON response."""
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=_make_snapshot(),
        ):
            response = app_client.get("/status?format=json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        data = response.json()
        assert data["timestamp"] == "2026-04-14T12:00:00Z"
        assert data["system"]["version"] == "1.0.0"
        assert len(data["collectors"]) == 1
        assert data["collectors"][0]["name"] == "DeviceCollector"

    def test_status_json_matches_snapshot_structure(self, app_client: TestClient) -> None:
        """The JSON output has the expected top-level keys."""
        with patch.object(
            app_client.app.state.exporter.status_service,
            "get_snapshot",
            return_value=_make_snapshot(),
        ):
            response = app_client.get("/status?format=json")

        data = response.json()
        assert set(data.keys()) == {"timestamp", "system", "collectors", "api_health", "data_freshness"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_status_endpoint.py -v`
Expected: FAIL with `AttributeError: 'ExporterApp' object has no attribute 'status_service'`

- [ ] **Step 3: Wire up StatusService and /status route in app.py**

In `src/meraki_dashboard_exporter/app.py`, add the import near the top (around line 34, with the other service imports):

```python
from .services.status import StatusService
```

In `ExporterApp.__init__()`, after the `self._discovery_summary` line (around line 80), add:

```python
        # Initialize status service for /status endpoint
        self.status_service = StatusService(
            collector_manager=self.collector_manager,
            expiration_manager=self.expiration_manager,
            client=self.client,
            settings=self.settings,
            start_time=self._start_time,
        )
```

In `create_app()`, after the `/clients` endpoint block (around line 643, before the `clear_dns_cache` endpoint), add the new route:

```python
        @app.get("/status", response_class=HTMLResponse)
        async def status(request: Request, format: str | None = None) -> HTMLResponse | JSONResponse:
            """Exporter self-health status dashboard."""
            exporter = app.state.exporter
            snapshot = exporter.status_service.get_snapshot()

            if format == "json":
                return JSONResponse(content=snapshot.to_dict())

            return app.state.templates.TemplateResponse(
                request,
                "status.html",
                context=snapshot.to_dict(),
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_status_endpoint.py -v`
Expected: All PASS

- [ ] **Step 5: Run linting**

Run: `uv run ruff check src/meraki_dashboard_exporter/app.py tests/unit/test_status_endpoint.py && uv run ruff format src/meraki_dashboard_exporter/app.py tests/unit/test_status_endpoint.py`
Expected: Clean or auto-fixed

- [ ] **Step 6: Commit**

```
git add src/meraki_dashboard_exporter/app.py tests/unit/test_status_endpoint.py
git commit -m "feat(status): wire up /status route with HTML and JSON responses"
```

---

### Task 6: Add /status Link to Index Page

**Files:**
- Modify: `src/meraki_dashboard_exporter/templates/index.html`

- [ ] **Step 1: Add the /status endpoint entry to the endpoint list**

In `src/meraki_dashboard_exporter/templates/index.html`, find the `/clients` endpoint block (around line 546-552):

```html
                <div class="endpoint">
                    <div class="endpoint-info">
                        <div class="endpoint-path">/clients</div>
                        <div class="endpoint-desc">Client data viewer - browse and search connected client information</div>
                    </div>
                    <a href="/clients" class="endpoint-link">View Clients</a>
                </div>
```

Immediately after this block (before the closing `</div>` of `endpoint-list`), add:

```html

                <div class="endpoint">
                    <div class="endpoint-info">
                        <div class="endpoint-path">/status</div>
                        <div class="endpoint-desc">Exporter self-health dashboard - collector status, API health, data freshness</div>
                    </div>
                    <a href="/status" class="endpoint-link">View Status</a>
                </div>
```

- [ ] **Step 2: Verify the edit is correct**

Run: `uv run python -c "from pathlib import Path; t = Path('src/meraki_dashboard_exporter/templates/index.html').read_text(); assert '/status' in t; assert 'View Status' in t; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```
git add src/meraki_dashboard_exporter/templates/index.html
git commit -m "feat(status): add /status link to index page navigation"
```

---

### Task 7: Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run all new tests**

Run: `uv run pytest tests/unit/test_status_service.py tests/unit/test_status_endpoint.py -v`
Expected: All PASS

- [ ] **Step 2: Run full test suite to check for regressions**

Run: `uv run pytest --tb=short -q`
Expected: All existing tests still pass

- [ ] **Step 3: Run linting and type checks on all changed files**

Run: `uv run ruff check src/meraki_dashboard_exporter/services/status.py src/meraki_dashboard_exporter/app.py tests/unit/test_status_service.py tests/unit/test_status_endpoint.py && uv run ruff format --check src/meraki_dashboard_exporter/services/status.py src/meraki_dashboard_exporter/app.py tests/unit/test_status_service.py tests/unit/test_status_endpoint.py`
Expected: Clean

- [ ] **Step 4: Run mypy on the new service module**

Run: `uv run mypy src/meraki_dashboard_exporter/services/status.py`
Expected: Clean or only pre-existing issues

- [ ] **Step 5: Commit any final fixes**

Only if steps 1-4 required changes. Otherwise skip.
