"""Native shutdown-observation contracts for #714."""
# ruff: noqa: D103

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from tests.harness.runner import (
    HarnessError,
    HarnessRunner,
    _barrier_order,
    _lifecycle_order,
)


def test_shutdown_barrier_requires_request_term_then_release() -> None:
    entries = [
        {"reason": "barrier:entered", "monotonic_seconds": 10.0},
        {"reason": "barrier:released", "monotonic_seconds": 12.0},
    ]

    ordering = _barrier_order(entries, term_monotonic_seconds=11.0)
    assert ordering["causal_order"] == "barrier:entered < host TERM < barrier:released"
    assert ordering["causal_basis"] == "shared_monotonic_test_clock"
    assert ordering["origin_entered_monotonic_seconds"] == 10.0
    assert ordering["host_term_monotonic_seconds"] == 11.0
    assert ordering["origin_released_monotonic_seconds"] == 12.0


def test_shutdown_barrier_rejects_release_before_term() -> None:
    entries = [
        {"reason": "barrier:entered", "monotonic_seconds": 10.0},
        {"reason": "barrier:released", "monotonic_seconds": 10.5},
    ]

    with pytest.raises(HarnessError, match="request:entered < TERM < barrier:released"):
        _barrier_order(entries, term_monotonic_seconds=11.0)


def test_shutdown_lifecycle_requires_dependency_order() -> None:
    logs: list[dict[str, object]] = [
        {"event": "Shutdown phase complete", "phase": "otel_metrics_stopped"},
        {"event": "Shutdown phase complete", "phase": "tracing_stopped"},
        {"event": "Shutdown phase complete", "phase": "otel_logging_stopped"},
        {"event": "Shutdown phase complete", "phase": "data_log_stopped"},
        {"event": "Shutdown phase complete", "phase": "dns_executor_drained"},
        {"event": "Shutdown phase complete", "phase": "sdk_executor_drained"},
        {"event": "Shutdown phase complete", "phase": "sdk_session_closed"},
        {"event": "Shutdown phase complete", "phase": "sdk_client_closed"},
        {"event": "Shutdown phase complete", "phase": "serving_executor_drained"},
        {"event": "Shutdown complete"},
    ]

    assert cast(list[str], _lifecycle_order(logs)["ordered_markers"])[-1] == "Shutdown complete"


def test_shutdown_lifecycle_rejects_missing_sdk_session_marker() -> None:
    logs: list[dict[str, object]] = [
        {"event": "Shutdown phase complete", "phase": "otel_metrics_stopped"},
        {"event": "Shutdown phase complete", "phase": "dns_executor_drained"},
        {"event": "Shutdown phase complete", "phase": "sdk_executor_drained"},
        {"event": "Shutdown phase complete", "phase": "sdk_client_closed"},
        {"event": "Shutdown phase complete", "phase": "serving_executor_drained"},
        {"event": "Shutdown complete"},
    ]

    with pytest.raises(HarnessError, match="sdk_session_closed"):
        _lifecycle_order(logs)


def test_shutdown_failure_retains_redacted_partial_evidence(tmp_path: Path) -> None:
    runner = HarnessRunner(tmp_path / "manifest.json", tmp_path / "artifacts", exporter_image="x")
    observation: dict[str, object] = {"logs": {"raw": "harness-sentinel-not-a-secret"}}

    runner._write_shutdown_observation(observation)

    retained = json.loads((tmp_path / "artifacts" / "shutdown-observation.json").read_text())
    assert retained["logs"]["raw"] == "[REDACTED]"


def test_shutdown_resolves_exact_compose_exporter_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = HarnessRunner(tmp_path / "manifest.json", tmp_path / "artifacts", exporter_image="x")
    calls: list[list[str]] = []

    class Result:
        stdout = "only-exporter\n"

    def fake_run(command: list[str], **_kwargs: object) -> Result:
        calls.append(command)
        return Result()

    monkeypatch.setattr("tests.harness.runner._run", fake_run)

    assert runner._exporter_container_id("exact-project", {}) == "only-exporter"
    assert calls == [
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            "label=com.docker.compose.project=exact-project",
            "--filter",
            "label=com.docker.compose.service=exporter",
        ]
    ]
