"""Tests for MR per-AP signal quality (RSSI/SNR) collector (#324)."""

from __future__ import annotations

import math
import time
from collections import Counter
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.devices.mr import signal_quality as sq_module
from meraki_dashboard_exporter.collectors.devices.mr.signal_quality import (
    MRSignalQualityCollector,
)
from meraki_dashboard_exporter.core.collector import MetricCollector
from meraki_dashboard_exporter.core.constants.metrics_constants import MRMetricName
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName, EndpointScheduler, OrgShape


def _make_gauge(name: object, description: str, labelnames: list[str]) -> Gauge:
    """Create a real Prometheus Gauge using the enum value as the metric name."""
    return Gauge(name.value if hasattr(name, "value") else name, description, labelnames)


def _ap(serial: str, network_id: str = "net1", model: str = "MR46", tags: list[str] | None = None):
    return {
        "serial": serial,
        "model": model,
        "networkId": network_id,
        "productType": "wireless",
        "tags": tags or [],
    }


# ----------------------------------------------------------------------
# Resumable fan-out cursor (#996)
# ----------------------------------------------------------------------

_SQ = EndpointGroupName.MR_SIGNAL_QUALITY


def _budget_settings(parent: MagicMock, *, deadline: int, rps: float, fraction: float) -> int:
    """Pin the inputs of the per-attempt budget and return the budget they give."""
    parent.settings.api.per_fetch_deadline_seconds = deadline
    parent.settings.api.rate_limit_requests_per_second = rps
    parent.settings.api.rate_limit_shared_fraction = fraction
    return math.floor(0.5 * deadline * rps * fraction)


def _called_serials(mock_api: MagicMock) -> list[str]:
    return [
        c.kwargs["deviceSerial"]
        for c in mock_api.wireless.getNetworkWirelessSignalQualityHistory.call_args_list
    ]


class TestMRSignalQualityCollector:
    """Test the per-AP signal quality collector."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Mock api."""
        api = MagicMock()
        api.wireless = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Mock parent."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.settings.api.concurrency_limit = 5
        parent.settings.collectors.collect_ap_signal_quality = True
        parent.settings.collectors.ap_signal_quality_tags = []
        parent.inventory = None
        parent.rate_limiter = None
        parent.scheduler = None
        parent._group_interval = MagicMock(return_value=3600.0)
        parent.collector_cadence_seconds = MagicMock(return_value=300.0)
        parent._create_gauge = MagicMock(side_effect=_make_gauge)
        parent._should_run_group = MagicMock(return_value=True)
        parent._group_ttl_seconds = MagicMock(return_value=None)
        parent._mark_group_ran = MagicMock()
        parent._set_metric = MagicMock()
        return parent

    @pytest.fixture
    def collector(self, mock_parent: MagicMock) -> MRSignalQualityCollector:
        """Collector."""
        return MRSignalQualityCollector(mock_parent)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def test_initialisation_creates_two_gauges(
        self, collector: MRSignalQualityCollector, mock_parent: MagicMock
    ) -> None:
        """Initialisation creates two gauges."""
        names = {c.args[0] for c in mock_parent._create_gauge.call_args_list}
        assert names == {MRMetricName.MR_SIGNAL_RSSI_DBM, MRMetricName.MR_SIGNAL_SNR_DB}
        for c in mock_parent._create_gauge.call_args_list:
            assert set(c.kwargs["labelnames"]) == {
                "org_id",
                "network_id",
                "serial",
                "model",
                "device_type",
            }

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    async def test_emits_newest_non_null_bucket(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Emits newest non null bucket."""
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[
                {
                    "startTs": "2026-07-03T09:00:00Z",
                    "endTs": "2026-07-03T10:00:00Z",
                    "snr": 30,
                    "rssi": -55,
                },
                {
                    "startTs": "2026-07-03T10:00:00Z",
                    "endTs": "2026-07-03T11:00:00Z",
                    "snr": 42,
                    "rssi": -48,
                },
                {
                    "startTs": "2026-07-03T11:00:00Z",
                    "endTs": "2026-07-03T12:00:00Z",
                    "snr": None,
                    "rssi": None,
                },
            ]
        )

        await collector.collect_signal_quality("org1", "Org", [_ap("Q1")])

        mock_api.wireless.getNetworkWirelessSignalQualityHistory.assert_called_once_with(
            "net1", deviceSerial="Q1", timespan=7200, resolution=3600, autoResolution=False
        )

        by_metric = {c.args[0]: c.args[2] for c in mock_parent._set_metric.call_args_list}
        assert by_metric[collector._mr_signal_rssi_dbm] == -48.0
        assert by_metric[collector._mr_signal_snr_db] == 42.0
        # Labels are ID-only std MR device set.
        labels = mock_parent._set_metric.call_args_list[0].args[1]
        assert labels["serial"] == "Q1"
        assert labels["model"] == "MR46"
        assert labels["device_type"] == "MR"
        assert "name" not in labels

    async def test_all_null_history_emits_nothing(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """All null history emits nothing."""
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"startTs": "x", "endTs": "y", "snr": None, "rssi": None}]
        )
        await collector.collect_signal_quality("org1", "Org", [_ap("Q1")])
        mock_parent._set_metric.assert_not_called()
        # Fan-out still ran → gate marked.
        mock_parent._mark_group_ran.assert_called_once_with(EndpointGroupName.MR_SIGNAL_QUALITY)

    async def test_fans_out_per_ap(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Fans out per ap."""
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"endTs": "z", "snr": 20, "rssi": -60}]
        )
        await collector.collect_signal_quality(
            "org1", "Org", [_ap("Q1"), _ap("Q2", network_id="net2")]
        )
        called_serials = {
            c.kwargs["deviceSerial"]
            for c in mock_api.wireless.getNetworkWirelessSignalQualityHistory.call_args_list
        }
        assert called_serials == {"Q1", "Q2"}

    # ------------------------------------------------------------------
    # AP selection
    # ------------------------------------------------------------------

    async def test_disabled_collects_nothing(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Disabled collects nothing."""
        mock_parent.settings.collectors.collect_ap_signal_quality = False
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(return_value=[])
        await collector.collect_signal_quality("org1", "Org", [_ap("Q1")])
        mock_api.wireless.getNetworkWirelessSignalQualityHistory.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_tag_scoping_selects_only_matching_aps(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Tag scoping selects only matching aps."""
        mock_parent.settings.collectors.ap_signal_quality_tags = ["monitored"]
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"endTs": "z", "snr": 10, "rssi": -70}]
        )
        devices = [
            _ap("Q-YES", tags=["monitored", "other"]),
            _ap("Q-NO", tags=["other"]),
            _ap("Q-NONE", tags=[]),
        ]
        await collector.collect_signal_quality("org1", "Org", devices)
        called_serials = {
            c.kwargs["deviceSerial"]
            for c in mock_api.wireless.getNetworkWirelessSignalQualityHistory.call_args_list
        }
        assert called_serials == {"Q-YES"}

    async def test_non_wireless_devices_ignored(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Non wireless devices ignored."""
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"endTs": "z", "snr": 10, "rssi": -70}]
        )
        switch = {"serial": "S1", "model": "MS220", "networkId": "net1", "productType": "switch"}
        await collector.collect_signal_quality("org1", "Org", [switch, _ap("Q1")])
        called = {
            c.kwargs["deviceSerial"]
            for c in mock_api.wireless.getNetworkWirelessSignalQualityHistory.call_args_list
        }
        assert called == {"Q1"}

    # ------------------------------------------------------------------
    # Scheduler gating
    # ------------------------------------------------------------------

    async def test_shed_group_skips_fetch(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """A group the scheduler has shed or the profile excludes fetches nothing (#996).

        The group is self-paced, so its own scheduler gate is never consulted;
        shedding and the collection profile still apply.
        """
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(return_value=[])
        mock_parent.scheduler = SimpleNamespace(
            profile_allows=lambda group: True, is_shed=lambda group: True
        )
        await collector.collect_signal_quality("org1", "Org", [_ap("Q1")])
        mock_parent.scheduler = SimpleNamespace(
            profile_allows=lambda group: False, is_shed=lambda group: False
        )
        await collector.collect_signal_quality("org1", "Org", [_ap("Q1")])
        mock_api.wireless.getNetworkWirelessSignalQualityHistory.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_fresh_ap_is_not_refetched_within_interval(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """An AP collected less than one interval ago is skipped (per-AP clock, #996)."""
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"endTs": "z", "snr": 20, "rssi": -60}]
        )
        await collector.collect_signal_quality("org1", "Org", [_ap("Q1")])
        await collector.collect_signal_quality("org1", "Org", [_ap("Q1")])
        assert mock_api.wireless.getNetworkWirelessSignalQualityHistory.call_count == 1
        mock_parent._should_run_group.assert_not_called()

    async def test_ttl_threaded_to_emissions(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Ttl threaded to emissions."""
        mock_parent._group_ttl_seconds = MagicMock(return_value=3600.0)
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"endTs": "z", "snr": 20, "rssi": -60}]
        )
        await collector.collect_signal_quality("org1", "Org", [_ap("Q1")])
        assert mock_parent._set_metric.call_args_list
        for c in mock_parent._set_metric.call_args_list:
            assert c.kwargs["ttl_seconds"] == 3600.0

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    async def test_error_shape_absorbed(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Error shape absorbed."""
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value={"errors": ["server error, retries exhausted"]}
        )
        await collector.collect_signal_quality("org1", "Org", [_ap("Q1")])
        mock_parent._set_metric.assert_not_called()

    async def test_per_ap_exception_isolated(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Per ap exception isolated."""

        def _side_effect(network_id, **kwargs):
            """Side effect."""
            if kwargs["deviceSerial"] == "Q-BAD":
                raise Exception("connection reset")
            return [{"endTs": "z", "snr": 20, "rssi": -60}]

        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            side_effect=_side_effect
        )
        await collector.collect_signal_quality(
            "org1", "Org", [_ap("Q-BAD"), _ap("Q-OK", network_id="net2")]
        )
        emitted_serials = {c.args[1]["serial"] for c in mock_parent._set_metric.call_args_list}
        assert emitted_serials == {"Q-OK"}

    # ------------------------------------------------------------------
    # Resumable fan-out cursor (#996)
    # ------------------------------------------------------------------

    async def test_three_attempts_cover_every_ap_once(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Three attempts over three budgets of APs fetch each AP exactly once (AC2)."""
        budget = _budget_settings(mock_parent, deadline=4, rps=2.5, fraction=0.8)
        assert budget == 4
        aps = [_ap(f"Q{i:02d}", network_id=f"net{i % 3}") for i in range(3 * budget)]
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"endTs": "z", "snr": 20, "rssi": -60}]
        )

        per_attempt: list[int] = []
        for attempt in range(3):
            before = len(_called_serials(mock_api))
            await collector.collect_signal_quality("org1", "Org", aps)
            per_attempt.append(len(_called_serials(mock_api)) - before)
            if attempt < 2:
                # A partial sweep is not a completed group run.
                mock_parent._mark_group_ran.assert_not_called()

        assert per_attempt == [budget, budget, budget]
        counts = Counter(_called_serials(mock_api))
        assert set(counts) == {ap["serial"] for ap in aps}
        assert set(counts.values()) == {1}
        mock_parent._mark_group_ran.assert_called_once_with(_SQ)
        mock_parent._should_run_group.assert_not_called()

        # The sweep is complete: a fourth attempt inside the interval fetches nothing.
        await collector.collect_signal_quality("org1", "Org", aps)
        assert len(_called_serials(mock_api)) == 3 * budget

    async def test_stale_aps_are_refetched_stalest_first(
        self,
        collector: MRSignalQualityCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Once the interval passes, the oldest readings are fetched first."""
        clock = {"now": 1000.0}
        monkeypatch.setattr(sq_module, "_monotonic", lambda: clock["now"])
        budget = _budget_settings(mock_parent, deadline=2, rps=2.5, fraction=0.8)
        assert budget == 2
        aps = [_ap(s) for s in ("A", "B", "C", "D")]
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"endTs": "z", "snr": 20, "rssi": -60}]
        )

        await collector.collect_signal_quality("org1", "Org", aps)  # A, B at t=1000
        clock["now"] = 1100.0
        await collector.collect_signal_quality("org1", "Org", aps)  # C, D at t=1100
        clock["now"] = 1100.0 + 3600.0  # all four are stale now
        await collector.collect_signal_quality("org1", "Org", aps)

        calls = _called_serials(mock_api)
        # Calls within one attempt run concurrently, so compare each attempt as a set.
        assert [set(calls[0:2]), set(calls[2:4]), set(calls[4:6])] == [
            {"A", "B"},
            {"C", "D"},
            {"A", "B"},
        ]
        assert len(calls) == 6

    async def test_failed_ap_is_retried_after_the_failure_spacing(
        self,
        collector: MRSignalQualityCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A failed AP is not stamped: a later attempt retries it, spaced like a group retry."""
        clock = {"now": 1000.0}
        monkeypatch.setattr(sq_module, "_monotonic", lambda: clock["now"])
        mock_parent.settings.scheduler.failure_retry_seconds = 300
        fail = {"Q-BAD": True}

        def _side_effect(network_id, **kwargs):
            """Fail Q-BAD until told otherwise."""
            if fail.get(kwargs["deviceSerial"]):
                raise Exception("connection reset")
            return [{"endTs": "z", "snr": 20, "rssi": -60}]

        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            side_effect=_side_effect
        )
        aps = [_ap("Q-BAD"), _ap("Q-OK", network_id="net2")]

        await collector.collect_signal_quality("org1", "Org", aps)
        clock["now"] = 1010.0
        await collector.collect_signal_quality("org1", "Org", aps)  # inside the spacing
        assert sorted(_called_serials(mock_api)) == ["Q-BAD", "Q-OK"]
        mock_parent._mark_group_ran.assert_not_called()

        fail["Q-BAD"] = False
        clock["now"] = 1300.0
        await collector.collect_signal_quality("org1", "Org", aps)
        assert _called_serials(mock_api)[-1] == "Q-BAD"
        assert len(_called_serials(mock_api)) == 3
        mock_parent._mark_group_ran.assert_called_once_with(_SQ)

    async def test_ap_leaving_the_selection_is_dropped_from_the_cursor(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """An AP no longer selected is pruned from the cursor on the next attempt (AC4)."""
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"endTs": "z", "snr": 20, "rssi": -60}]
        )
        await collector.collect_signal_quality("org1", "Org", [_ap("Q1"), _ap("Q2")])
        assert set(collector._cursor.last_success) == {"Q1", "Q2"}

        # Q2 loses its tag: it leaves the selection.
        mock_parent.settings.collectors.ap_signal_quality_tags = ["monitored"]
        await collector.collect_signal_quality(
            "org1", "Org", [_ap("Q1", tags=["monitored"]), _ap("Q2")]
        )
        assert set(collector._cursor.last_success) == {"Q1"}
        assert set(collector._cursor.last_attempt) == {"Q1"}

    async def test_ttl_outlives_a_multi_attempt_sweep(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Series emitted by an oversized sweep carry a TTL longer than the sweep."""
        budget = _budget_settings(mock_parent, deadline=4, rps=2.5, fraction=0.8)
        mock_parent._group_ttl_seconds = MagicMock(return_value=7200.0)
        aps = [_ap(f"Q{i}") for i in range(10 * budget)]
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"endTs": "z", "snr": 20, "rssi": -60}]
        )
        await collector.collect_signal_quality("org1", "Org", aps)
        ttls = {c.kwargs["ttl_seconds"] for c in mock_parent._set_metric.call_args_list}
        # interval 3600 + 10 passes x 300 s cadence, at the group's 2x multiplier.
        assert ttls == {2.0 * (3600.0 + 10 * 300.0)}


def _scheduler_settings() -> SimpleNamespace:
    """Settings carrying everything the scheduler and the sub-collector read."""
    return SimpleNamespace(
        api=SimpleNamespace(
            concurrency_limit=1,
            per_fetch_deadline_seconds=1,
            rate_limit_requests_per_second=5.0,
            rate_limit_shared_fraction=0.8,
            model_fields_set=set(),
        ),
        collectors=SimpleNamespace(
            profile="full", collect_ap_signal_quality=True, ap_signal_quality_tags=[]
        ),
        monitoring=SimpleNamespace(metric_ttl_multiplier=2.0),
        scheduler=SimpleNamespace(
            mode="fixed",
            target_utilization=0.7,
            max_stretch_factor=4.0,
            max_interval_seconds=3600,
            resolve_interval_seconds=900,
            aimd_enabled=False,
            aimd_resolve_hysteresis=0.2,
            group_interval_overrides={},
            failure_retry_seconds=300,
        ),
    )


class _AmpleLimiter:
    def effective_rate_per_second(self) -> float:
        return math.inf


async def test_spent_budget_ends_cleanly_and_records_no_scheduler_failure() -> None:
    """An attempt that spends its budget returns normally and fails nothing (AC3).

    Each fetch takes 0.2 s against a 1 s per-fetch deadline. The budget
    (0.5 x 1 s x 4 rps = 2 APs) finishes inside the deadline; fetching all eight
    APs in one pass would be cancelled by it and leave the group failed.
    """
    settings = _scheduler_settings()
    scheduler = EndpointScheduler(settings, _AmpleLimiter())  # type: ignore[arg-type]
    scheduler.register_groups(DeviceCollector.endpoint_groups)
    zeros = dict.fromkeys(
        (
            "network_count switch_network_count appliance_network_count sensor_network_count "
            "camera_network_count cellular_network_count device_count switch_count "
            "appliance_count physical_mx_count camera_count sensor_count cellular_count"
        ).split(),
        0,
    )
    scheduler.resolve(
        OrgShape(
            org_id="996",
            wireless_network_count=1,
            ap_count=8,
            signal_quality_ap_count=8,
            **zeros,
        )
    )

    api = MagicMock()

    def _slow(network_id, **kwargs):
        time.sleep(0.2)
        return [{"endTs": "z", "snr": 20, "rssi": -60}]

    api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(side_effect=_slow)

    parent = MagicMock()
    parent.api = api
    parent.settings = settings
    parent.rate_limiter = None
    parent.scheduler = scheduler
    parent._force_run = False
    parent._endpoint_group_verdicts = {}
    parent._create_gauge = MagicMock(side_effect=_make_gauge)
    parent._set_metric = MagicMock()
    parent.collector_cadence_seconds = MagicMock(return_value=300.0)
    for name in (
        "_should_run_group",
        "_mark_group_ran",
        "_mark_group_failed",
        "_set_endpoint_group_verdict",
        "_finalize_endpoint_group_verdicts",
        "_group_interval",
        "_group_ttl_seconds",
    ):
        setattr(parent, name, MethodType(getattr(MetricCollector, name), parent))

    collector = MRSignalQualityCollector(parent)
    await collector.collect_signal_quality("org1", "Org", [_ap(f"Q{i}") for i in range(8)])
    parent._track_error.assert_not_called()
    parent._finalize_endpoint_group_verdicts()

    assert api.wireless.getNetworkWirelessSignalQualityHistory.call_count == 2
    assert _SQ not in parent._endpoint_group_verdicts
    assert scheduler._failed_attempt.get(_SQ) is None
    assert scheduler._last_attempt.get(_SQ) is None


def test_per_attempt_budget_defaults_to_480_calls() -> None:
    """Shipped defaults: 0.5 x 120 s x (10 rps x 0.8) = 480 single-call items."""
    settings = SimpleNamespace(
        api=SimpleNamespace(
            per_fetch_deadline_seconds=120,
            rate_limit_requests_per_second=10,
            rate_limit_shared_fraction=0.8,
        )
    )
    assert sq_module.per_attempt_call_budget(settings, None) == 480
    assert sq_module.per_attempt_call_budget(settings, None, calls_per_item=8) == 60
    limiter = SimpleNamespace(effective_rate_per_second=lambda: 4.0)
    assert sq_module.per_attempt_call_budget(settings, limiter) == 240
    assert sq_module.per_attempt_call_budget(MagicMock(), MagicMock()) == 480


def test_sweep_ttl_is_unchanged_for_a_fleet_that_fits_one_attempt() -> None:
    """Fleets inside one budget keep the group TTL exactly."""
    assert sq_module.sweep_ttl_seconds(7200.0, 3600.0, 480, 480, 300.0) == 7200.0
    assert sq_module.sweep_ttl_seconds(None, 3600.0, 5000, 480, 300.0) is None
    assert sq_module.sweep_ttl_seconds(7200.0, 3600.0, 481, 480, 300.0) == 2.0 * (
        3600.0 + 2 * 300.0
    )
