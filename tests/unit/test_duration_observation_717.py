"""Contracts for the scheduled DeviceCollector duration observation (#717)."""
# ruff: noqa: D103

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.harness.runner import (
    HarnessError,
    HarnessRunner,
    _baseline_cache_evidence,
    _duration_observation,
    _histogram_values,
    _post_boundary_cache_lineage,
    _post_boundary_verified_paths,
    _processing_evidence,
)

METRICS = """\
# TYPE meraki_exporter_collector_duration_seconds histogram
meraki_exporter_collector_duration_seconds_sum{collector="DeviceCollector"} 0.75
meraki_exporter_collector_duration_seconds_count{collector="DeviceCollector"} 3
"""


def test_duration_observation_requires_exact_one_successful_idle_device_run() -> None:
    """The native acceptance contract fails closed on scheduler interference."""
    pre: dict[str, object] = {
        "histogram": _histogram_values(METRICS),
        "status": {
            "total_runs": 7,
            "total_successes": 6,
            "total_failures": 1,
            "is_running": False,
            "last_success_time": 100.0,
        },
        "scheduler": {"attempts": 4, "last_success_timestamp_seconds": 100.0},
    }
    post: dict[str, object] = {
        "histogram": _histogram_values(METRICS.replace("0.75", "1.25").replace(" 3", " 4")),
        "status": {
            "total_runs": 8,
            "total_successes": 7,
            "total_failures": 1,
            "is_running": False,
            "last_success_time": 101.0,
        },
        "scheduler": {"attempts": 4, "last_success_timestamp_seconds": 100.0},
    }

    observation = _duration_observation(pre, post, elapsed_seconds=1.0)

    assert observation["deltas"] == {
        "histogram_count": 1,
        "histogram_sum_seconds": 0.5,
        "mean_seconds": 0.5,
        "total_runs": 1,
        "total_successes": 1,
        "total_failures": 0,
        "last_success_time_seconds": 1.0,
    }
    assert observation["acceptance"] == "passed"

    post["status"] = {
        "total_runs": 9,
        "total_successes": 7,
        "total_failures": 1,
        "is_running": False,
        "last_success_time": 101.0,
    }
    with pytest.raises(HarnessError, match="total_runs delta must equal 1"):
        _duration_observation(pre, post, elapsed_seconds=1.0)

    post["status"] = {
        "total_runs": 8,
        "total_successes": 7,
        "total_failures": 1,
        "is_running": False,
        "last_success_time": 101.0,
    }
    post["scheduler"] = {"attempts": 5, "last_success_timestamp_seconds": 101.0}
    with pytest.raises(HarnessError, match="scheduler attempts"):
        _duration_observation(pre, post, elapsed_seconds=1.0)


def test_duration_observation_rejects_any_upstream_request_after_boundary() -> None:
    """A warmed wrapper-only run must never reach the replay origin."""
    paths = {
        "/api/v1/organizations/org_001",
        "/api/v1/organizations/org_001/networks",
        "/api/v1/organizations/org_001/devices",
        "/api/v1/organizations/org_001/devices/availabilities",
    }
    journal = "\n".join(
        json.dumps({"path": path, "reason": "matched", "evidence": "verified fixture"})
        for path in paths
    )

    assert _post_boundary_verified_paths(journal, len(journal.splitlines()), paths) == paths
    with pytest.raises(HarnessError, match="upstream request"):
        _post_boundary_verified_paths(journal, 0, set())


def test_duration_lineage_requires_warm_cache_hits_and_processing_branch() -> None:
    """The post-boundary proof is cache lineage, not impossible replay duplication."""
    logs = [
        {"event": "Cache hit for organizations", "cache_age_seconds": 0.1},
        {"event": "Cache hit for networks", "cache_age_seconds": 0.1},
        {"event": "Cache hit for devices", "cache_age_seconds": 0.1},
        {"event": "Starting parallel organization processing", "org_count": 1},
        {
            "event": "Processing devices",
            "device_count": 1,
            "availability_count": 0,
            "availability_due": False,
        },
    ]
    _post_boundary_cache_lineage(logs)
    _processing_evidence(logs)
    with pytest.raises(HarnessError, match="missing post-boundary cache hits"):
        _post_boundary_cache_lineage(logs[1:])
    with pytest.raises(HarnessError, match="cache mutation"):
        _post_boundary_cache_lineage([
            *logs,
            {"event": "Cache miss for devices, fetching from API"},
        ])
    with pytest.raises(HarnessError, match="processing evidence"):
        _processing_evidence([
            entry for entry in logs if entry.get("event") != "Processing devices"
        ])


def test_duration_baseline_requires_nonempty_cache_population() -> None:
    """Cache hits alone do not prove that the warmed cache contains corpus data."""
    logs = [
        {"event": "Updated organization cache", "org_count": 1},
        {"event": "Updated network cache", "network_count": 1},
        {"event": "Updated device cache", "device_count": 1},
        {"event": "Updated device availabilities cache", "device_count": 1},
    ]
    assert _baseline_cache_evidence(logs)
    logs[-1]["device_count"] = 0
    assert not _baseline_cache_evidence(logs)


def test_duration_snapshot_authenticates_the_sensitive_status_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The disposable control token must also authenticate the protected status read."""
    captured_command: list[str] = []
    status = {
        "collectors": [
            {
                "name": "DeviceCollector",
                "total_runs": 1,
                "total_successes": 1,
                "total_failures": 0,
                "is_running": False,
                "last_success_time": 1.0,
            }
        ],
        "scheduler": {
            "groups": [
                {
                    "name": "device_availability",
                    "attempts": 1,
                    "last_success_timestamp_seconds": 1.0,
                }
            ]
        },
    }

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured_command.extend(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({
                "metrics_status": 200,
                "metrics_raw": METRICS,
                "status_status": 200,
                "status_raw": json.dumps(status),
            }),
            stderr="",
        )

    monkeypatch.setattr("tests.harness.runner._run", fake_run)
    runner = HarnessRunner(
        Path("unused-manifest.json"),
        Path("unused-artifacts"),
        exporter_image="unused-image",
    )

    runner._capture_duration_snapshot([], {})

    script = captured_command[-1]
    assert "Authorization" in script
    assert "MERAKI_EXPORTER_SERVER__API_TOKEN" in script


def test_duration_failure_evidence_redacts_the_disposable_status_token(tmp_path: Path) -> None:
    """Retained partial evidence cannot leak the disposable status token."""
    runner = HarnessRunner(Path("unused-manifest.json"), tmp_path, exporter_image="unused-image")
    runner._write_duration_observation({
        "acceptance": "failed",
        "error": "harness-control-token-not-a-secret",
    })
    written = (tmp_path / "duration-observation.json").read_text(encoding="utf-8")
    assert "[REDACTED]" in written
    assert "acceptance" in written


def test_duration_baseline_retries_while_the_first_histogram_sample_is_pending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Startup can be probeable before the initial collector observation exists."""
    path = "/api/v1/organizations/org_001/devices"
    (tmp_path / "journal.jsonl").write_text(
        json.dumps({"path": path, "reason": "matched", "evidence": "verified fixture"}) + "\n",
        encoding="utf-8",
    )
    snapshot: dict[str, object] = {
        "metrics_raw": METRICS,
        "histogram": _histogram_values(METRICS),
        "status": {
            "total_runs": 1,
            "total_successes": 1,
            "total_failures": 0,
            "is_running": False,
            "last_success_time": 1.0,
        },
        "scheduler": {"attempts": 1, "last_success_timestamp_seconds": 1.0},
    }
    calls = 0

    def capture(*_: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HarnessError("DeviceCollector duration histogram sum was absent")
        return snapshot

    runner = HarnessRunner(
        Path("unused-manifest.json"),
        Path("unused-artifacts"),
        exporter_image="unused-image",
    )
    monkeypatch.setattr(runner, "_capture_duration_snapshot", capture)
    monkeypatch.setattr("tests.harness.runner.time.sleep", lambda _: None)
    monkeypatch.setattr("tests.harness.runner._duration_logs", lambda *_: "")
    monkeypatch.setattr("tests.harness.runner._baseline_fixture_evidence", lambda *_: True)
    monkeypatch.setattr("tests.harness.runner._baseline_cache_evidence", lambda *_: True)
    monkeypatch.setattr("tests.harness.runner._product_metric_evidence", lambda *_: ["product"])

    assert runner._wait_for_duration_baseline([], {}, tmp_path, {path}) == snapshot
    assert calls == 3


def test_duration_baseline_ignores_probe_access_lines_when_structured_events_are_stable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The baseline probes themselves append access logs but no new exporter state events."""
    path = "/api/v1/organizations/org_001/devices"
    (tmp_path / "journal.jsonl").write_text("", encoding="utf-8")
    snapshot: dict[str, object] = {
        "metrics_raw": METRICS,
        "histogram": _histogram_values(METRICS),
        "status": {
            "total_runs": 1,
            "total_successes": 1,
            "total_failures": 0,
            "is_running": False,
            "last_success_time": 1.0,
        },
        "scheduler": {"attempts": 1, "last_success_timestamp_seconds": 1.0},
    }
    log_snapshots = iter([
        '127.0.0.1 - "GET /metrics" 200\n',
        '127.0.0.1 - "GET /metrics" 200\n127.0.0.1 - "GET /status" 200\n',
    ])
    monotonic = iter([0.0, 0.1, 41.0])
    runner = HarnessRunner(
        Path("unused-manifest.json"),
        Path("unused-artifacts"),
        exporter_image="unused-image",
    )
    monkeypatch.setattr(runner, "_capture_duration_snapshot", lambda *_: snapshot)
    monkeypatch.setattr("tests.harness.runner._duration_logs", lambda *_: next(log_snapshots))
    monkeypatch.setattr("tests.harness.runner.time.monotonic", lambda: next(monotonic))
    monkeypatch.setattr("tests.harness.runner.time.sleep", lambda _: None)
    monkeypatch.setattr("tests.harness.runner._baseline_fixture_evidence", lambda *_: True)
    monkeypatch.setattr("tests.harness.runner._baseline_cache_evidence", lambda *_: True)
    monkeypatch.setattr("tests.harness.runner._product_metric_evidence", lambda *_: ["product"])

    assert runner._wait_for_duration_baseline([], {}, tmp_path, {path}) == snapshot
