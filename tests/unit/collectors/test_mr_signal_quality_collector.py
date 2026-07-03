"""Tests for MR per-AP signal quality (RSSI/SNR) collector (#324)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mr.signal_quality import (
    MRSignalQualityCollector,
)
from meraki_dashboard_exporter.core.constants.metrics_constants import MRMetricName
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName


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

    async def test_gate_closed_skips_fetch(
        self, collector: MRSignalQualityCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """Gate closed skips fetch."""
        mock_parent._should_run_group = MagicMock(return_value=False)
        mock_api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(return_value=[])
        await collector.collect_signal_quality("org1", "Org", [_ap("Q1")])
        mock_api.wireless.getNetworkWirelessSignalQualityHistory.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

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
