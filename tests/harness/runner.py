"""Executable, offline Docker Compose runner for the failure replay harness."""
# ruff: noqa: D102, D103, D107

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Final

from .corpus import CorpusError, load_manifest
from .server import FaultMode, fault_decision
from .tls import create_tls_material

DEFAULT_MANIFEST: Final = Path("tests/harness/corpus/manifest.json")
COMPOSE_FILE: Final = Path("tests/harness/compose.yml")
PROXY_DOCKERFILE: Final = Path("tests/harness/Dockerfile")
COMPOSE_TEARDOWN_TIMEOUT_SECONDS: Final = 30
DURATION_OBSERVATION_TIMEOUT_SECONDS: Final = 90
DURATION_OBSERVATION_CONTROL_TOKEN: Final = "harness-control-token-not-a-secret"
_DURATION_METRIC: Final = "meraki_exporter_collector_duration_seconds"
SHUTDOWN_BARRIER_TIMEOUT_SECONDS: Final = 40
SHUTDOWN_RUNNING_PROOF_SECONDS: Final = 0.5
SHUTDOWN_EXIT_TIMEOUT_SECONDS: Final = 30
SHUTDOWN_GRACE_PERIOD_SECONDS: Final = 150


class HarnessError(RuntimeError):
    """The harness cannot establish its closed, locally-built execution boundary."""


def image_id(image: str) -> str:
    """Return only a local immutable image ID, never a mutable image tag."""
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        check=True,
        text=True,
        capture_output=True,
    )
    resolved = result.stdout.strip()
    if not resolved.startswith("sha256:") or len(resolved) != 71:
        raise HarnessError(f"image {image!r} did not resolve to a sha256 image ID")
    return resolved


def image_label(image: str, label: str) -> str:
    """Read a provenance label from a local image."""
    result = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            f'{{{{ index .Config.Labels "{label}" }}}}',
            image,
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


class HarnessRunner:
    """Creates run-local material, drives Compose, probes exporter, then tears it down."""

    def __init__(
        self,
        manifest: Path,
        artifacts: Path,
        *,
        exporter_image: str,
        build_exporter: bool = False,
        target_operation: str | None = None,
    ) -> None:
        self.manifest = manifest
        self.artifacts = artifacts
        self.exporter_image = exporter_image
        self.build_exporter = build_exporter
        self.target_operation = target_operation
        self._last_teardown_fallback = False

    def run(self, modes: list[FaultMode]) -> None:
        corpus = load_manifest(self.manifest, require_real=True)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        exporter_id, proxy_id = self._build_images()
        evidence: list[dict[str, object]] = []
        expected_paths = {fixture.path for fixture in corpus.fixtures}
        for mode in modes:
            try:
                evidence.append(
                    self._run_mode(
                        mode, exporter_id, proxy_id, len(corpus.fixtures), expected_paths
                    )
                )
            except Exception as error:
                evidence.append({
                    "mode": mode.value,
                    "observed": False,
                    "error": str(error),
                    "teardown_fallback": self._last_teardown_fallback,
                })
                self._write_evidence(evidence)
                raise
            self._write_evidence(evidence)

    def observe_duration(self) -> None:
        """Prove one scheduled DeviceCollector wrapper run observes the histogram once."""
        corpus = load_manifest(self.manifest, require_real=True)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        exporter_id, proxy_id = self._build_images()
        expected_paths = {fixture.path for fixture in corpus.fixtures}
        with tempfile.TemporaryDirectory(prefix="duration-observation-") as temporary:
            runtime = Path(temporary)
            shutil.copytree(self.manifest.parent, runtime / "corpus")
            create_tls_material(runtime)
            (runtime / "journal.jsonl").touch(mode=0o666)
            project = f"duration-observation-{int(time.time() * 1000)}"
            env = {
                "HARNESS_IMAGE_ID": exporter_id,
                "HARNESS_PROXY_IMAGE_ID": proxy_id,
                "HARNESS_RUNTIME_DIR": str(runtime),
                "HARNESS_MODE": FaultMode.BASELINE.value,
                "HARNESS_TARGET_OPERATION": "",
                "HARNESS_ORIGIN_HOST": "replay-origin",
                "HARNESS_TRUSTED_CA": "trusted-ca.pem",
            }
            command = [
                "docker",
                "compose",
                "--project-name",
                project,
                "--env-file",
                "/dev/null",
                "-f",
                str(COMPOSE_FILE),
            ]
            teardown: dict[str, object] = {"fallback_required": False}
            observation: dict[str, object] = {
                "schema_version": 2,
                "acceptance": "pending",
                "collector": "DeviceCollector",
                "image_ids": {"exporter": exporter_id, "proxy": proxy_id},
                "manifest_provenance": _manifest_provenance(self.manifest, corpus),
            }
            try:
                _run([*command, "up", "--detach", "--no-build"], env=env)
                self._probe_exporter(command, env)
                pre = self._wait_for_duration_baseline(command, env, runtime, expected_paths)
                journal_before = (runtime / "journal.jsonl").read_text(encoding="utf-8")
                logs_before = _duration_logs(command, env)
                boundary = len(journal_before.splitlines())
                log_boundary = len(logs_before.splitlines())
                wall_started = time.time()
                monotonic_started = time.monotonic()
                observation.update({
                    "observation_mode": "natural_scheduler_wrapper",
                    "journal_line_boundary": boundary,
                    "exporter_log_line_boundary": log_boundary,
                    "pre": pre,
                    "journal": {"before": journal_before},
                    "logs": {"before": logs_before},
                    "product_metric_evidence": _product_metric_evidence(pre["metrics_raw"]),
                    "observation_times": {
                        "wall_started_seconds": wall_started,
                        "monotonic_started_seconds": monotonic_started,
                    },
                })
                post, elapsed = self._wait_for_duration_completion(
                    command, env, pre, monotonic_started
                )
                wall_finished = time.time()
                monotonic_finished = time.monotonic()
                observation["post"] = post
                observation["observation_times"] = {
                    "wall_started_seconds": wall_started,
                    "wall_finished_seconds": wall_finished,
                    "monotonic_started_seconds": monotonic_started,
                    "monotonic_finished_seconds": monotonic_finished,
                }
                observation.update(
                    _duration_observation(
                        pre,
                        post,
                        elapsed_seconds=elapsed,
                        observation_window=(wall_started, wall_finished),
                    )
                )
                journal_after = (runtime / "journal.jsonl").read_text(encoding="utf-8")
                logs_after = _duration_logs(command, env)
                post_logs = _parse_json_logs(logs_after.splitlines()[log_boundary:])
                _post_boundary_cache_lineage(post_logs)
                _processing_evidence(post_logs)
                _post_boundary_verified_paths(journal_after, boundary, set())
                observation.update({
                    "schema_version": 2,
                    "collector": "DeviceCollector",
                    "acceptance_stage": "completed",
                    "image_ids": {"exporter": exporter_id, "proxy": proxy_id},
                    "manifest_provenance": _manifest_provenance(self.manifest, corpus),
                    "observation_mode": "natural_scheduler_wrapper",
                    "journal_line_boundary": boundary,
                    "exporter_log_line_boundary": log_boundary,
                    "journal": {
                        "before": journal_before,
                        "after": journal_after,
                        "before_parsed": _journal_entries(journal_before),
                        "after_parsed": _journal_entries(journal_after),
                        "suffix": "",
                    },
                    "logs": {
                        "before": logs_before,
                        "after": logs_after,
                        "post_boundary_parsed": post_logs,
                    },
                    "pre": pre,
                    "post": post,
                    "product_metric_evidence": _product_metric_evidence(pre["metrics_raw"]),
                })
                self._write_duration_observation(observation)
            except Exception as error:
                # Preserve every candidate collected before the failing gate; teardown is separate.
                candidate = observation
                candidate.update({
                    "schema_version": 2,
                    "acceptance": "failed",
                    "failure_stage": "duration_observation",
                    "error": str(error),
                    "image_ids": {"exporter": exporter_id, "proxy": proxy_id},
                })
                for name, value in (("pre", locals().get("pre")), ("post", locals().get("post"))):
                    if isinstance(value, dict):
                        candidate[name] = value
                current_journal = (runtime / "journal.jsonl").read_text(encoding="utf-8")
                journal_candidate = candidate.get("journal")
                if not isinstance(journal_candidate, dict):
                    journal_candidate = {}
                journal_boundary = candidate.get("journal_line_boundary")
                suffix = (
                    current_journal.splitlines()[journal_boundary:]
                    if isinstance(journal_boundary, int)
                    else current_journal.splitlines()
                )
                journal_candidate.update({
                    "after": current_journal,
                    "after_parsed": _journal_entries(current_journal),
                    "suffix_parsed": _journal_entries("\n".join(suffix)),
                })
                candidate["journal"] = journal_candidate
                current_logs = _duration_logs(command, env, check=False)
                logs_candidate = candidate.get("logs")
                if not isinstance(logs_candidate, dict):
                    logs_candidate = {}
                log_boundary_value = candidate.get("exporter_log_line_boundary")
                post_log_lines = (
                    current_logs.splitlines()[log_boundary_value:]
                    if isinstance(log_boundary_value, int)
                    else current_logs.splitlines()
                )
                logs_candidate.update({
                    "after": current_logs,
                    "post_boundary_parsed": _parse_json_logs(post_log_lines),
                })
                candidate["logs"] = logs_candidate
                self._write_duration_observation(candidate)
                raise
            finally:
                try:
                    self._teardown(command, env, project, teardown)
                finally:
                    (self.artifacts / "teardown-duration-observation.json").write_text(
                        _redact(json.dumps(teardown, indent=2, sort_keys=True)) + "\n",
                        encoding="utf-8",
                    )

    def observe_shutdown(self) -> None:
        """Prove SIGTERM waits for a blocked SDK worker before clean process exit."""
        corpus = load_manifest(self.manifest, require_real=True)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        exporter_id, proxy_id = self._build_images()
        target = self.target_operation or corpus.fixtures[0].sdk_operation
        target_fixture = next(
            (item for item in corpus.fixtures if item.sdk_operation == target), None
        )
        if target_fixture is None:
            raise HarnessError(f"shutdown target operation {target!r} is absent from the corpus")
        with tempfile.TemporaryDirectory(prefix="shutdown-observation-") as temporary:
            runtime = Path(temporary)
            shutil.copytree(self.manifest.parent, runtime / "corpus")
            create_tls_material(runtime)
            (runtime / "journal.jsonl").touch(mode=0o666)
            project = f"shutdown-observation-{int(time.time() * 1000)}"
            env = {
                "HARNESS_IMAGE_ID": exporter_id,
                "HARNESS_PROXY_IMAGE_ID": proxy_id,
                "HARNESS_RUNTIME_DIR": str(runtime),
                "HARNESS_MODE": FaultMode.TIMEOUT.value,
                "HARNESS_TARGET_OPERATION": target,
                "HARNESS_ORIGIN_HOST": "replay-origin",
                "HARNESS_TRUSTED_CA": "trusted-ca.pem",
            }
            command = [
                "docker",
                "compose",
                "--project-name",
                project,
                "--env-file",
                "/dev/null",
                "-f",
                str(COMPOSE_FILE),
            ]
            teardown: dict[str, object] = {"fallback_required": False}
            observation: dict[str, object] = {
                "schema_version": 1,
                "acceptance": "pending",
                "observation_mode": "blocked_sdk_worker_sigterm",
                "target_operation": target,
                "target_path": target_fixture.path,
                "image_ids": {"exporter": exporter_id, "proxy": proxy_id},
                "manifest_provenance": _manifest_provenance(self.manifest, corpus),
            }
            container_id: str | None = None
            try:
                _run([*command, "up", "--detach", "--no-build"], env=env)
                container_id = self._exporter_container_id(project, env)
                observation["exporter_container_id"] = container_id
                entered = self._wait_for_shutdown_barrier(runtime, target_fixture.path)
                term_wall, term_monotonic = time.time(), time.monotonic()
                term_journal_boundary = len(
                    (runtime / "journal.jsonl").read_text(encoding="utf-8").splitlines()
                )
                observation["term"] = {
                    "wall_seconds": term_wall,
                    "monotonic_seconds": term_monotonic,
                    "journal_line_boundary": term_journal_boundary,
                }
                _run(
                    ["docker", "kill", "--signal", "TERM", container_id],
                    env=env,
                    timeout=COMPOSE_TEARDOWN_TIMEOUT_SECONDS,
                )
                self._prove_container_remains_running(container_id, env)
                release_wall, release_monotonic = time.time(), time.monotonic()
                (runtime / "barrier-release").write_text("released\n", encoding="utf-8")
                exit_code, elapsed = self._wait_for_container_exit(container_id, env)
                elapsed_after_term = time.monotonic() - term_monotonic
                if exit_code != 0:
                    raise HarnessError(f"exporter exited with code {exit_code}, expected 0")
                if elapsed_after_term > SHUTDOWN_GRACE_PERIOD_SECONDS:
                    raise HarnessError("exporter did not exit within the 150-second default grace")
                journal = (runtime / "journal.jsonl").read_text(encoding="utf-8")
                logs = self._container_logs(container_id, env)
                entries, parsed_logs = (
                    _journal_entries(journal),
                    _parse_json_logs(logs.splitlines()),
                )
                observation.update({
                    "barrier": {
                        "entered": entered,
                        "release_written": {
                            "wall_seconds": release_wall,
                            "monotonic_seconds": release_monotonic,
                        },
                        "ordering": _barrier_order(
                            entries,
                            term_monotonic_seconds=term_monotonic,
                            target_path=target_fixture.path,
                            term_journal_boundary=term_journal_boundary,
                        ),
                    },
                    "exit": {
                        "code": exit_code,
                        "elapsed_after_release_seconds": elapsed,
                        "elapsed_after_term_seconds": elapsed_after_term,
                        "grace_period_seconds": SHUTDOWN_GRACE_PERIOD_SECONDS,
                    },
                    "journal": {"raw": journal, "parsed": entries},
                    "logs": {"raw": logs, "parsed": parsed_logs},
                    "lifecycle": _lifecycle_order(parsed_logs),
                    "acceptance": "passed",
                })
                self._write_shutdown_observation(observation)
            except Exception as error:
                observation.update({"acceptance": "failed", "error": str(error)})
                journal = (runtime / "journal.jsonl").read_text(encoding="utf-8")
                observation["journal"] = {"raw": journal, "parsed": _journal_entries(journal)}
                if container_id is not None:
                    logs = self._container_logs(container_id, env)
                    observation["logs"] = {
                        "raw": logs,
                        "parsed": _parse_json_logs(logs.splitlines()),
                    }
                self._write_shutdown_observation(observation)
                raise
            finally:
                try:
                    self._teardown(command, env, project, teardown)
                finally:
                    (self.artifacts / "teardown-shutdown-observation.json").write_text(
                        _redact(json.dumps(teardown, indent=2, sort_keys=True)) + "\n",
                        encoding="utf-8",
                    )

    def _write_shutdown_observation(self, observation: dict[str, object]) -> None:
        self.artifacts.mkdir(parents=True, exist_ok=True)
        (self.artifacts / "shutdown-observation.json").write_text(
            _redact(json.dumps(observation, indent=2, sort_keys=True)) + "\n", encoding="utf-8"
        )

    def _exporter_container_id(self, project: str, env: dict[str, str]) -> str:
        result = _run(
            [
                "docker",
                "ps",
                "--all",
                "--quiet",
                "--filter",
                f"label=com.docker.compose.project={project}",
                "--filter",
                "label=com.docker.compose.service=exporter",
            ],
            env=env,
            timeout=COMPOSE_TEARDOWN_TIMEOUT_SECONDS,
        )
        container_ids = [line for line in result.stdout.splitlines() if line]
        if len(container_ids) != 1:
            raise HarnessError(
                "could not resolve exactly one exporter container for shutdown proof"
            )
        return container_ids[0]

    def _wait_for_shutdown_barrier(self, runtime: Path, target_path: str) -> dict[str, object]:
        deadline = time.monotonic() + SHUTDOWN_BARRIER_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            entries = _journal_entries((runtime / "journal.jsonl").read_text(encoding="utf-8"))
            if entry := next(
                (
                    item
                    for item in entries
                    if item.get("reason") == "barrier:entered" and item.get("path") == target_path
                ),
                None,
            ):
                return entry
            time.sleep(0.05)
        raise HarnessError(
            "target SDK request did not enter the shutdown barrier within 40 seconds"
        )

    def _prove_container_remains_running(self, container_id: str, env: dict[str, str]) -> None:
        deadline = time.monotonic() + SHUTDOWN_RUNNING_PROOF_SECONDS
        while time.monotonic() < deadline:
            result = _run(
                ["docker", "inspect", "--format", "{{.State.Running}}", container_id],
                env=env,
                timeout=COMPOSE_TEARDOWN_TIMEOUT_SECONDS,
            )
            if result.stdout.strip() != "true":
                raise HarnessError("exporter exited while the shutdown barrier remained closed")
            time.sleep(0.05)

    def _wait_for_container_exit(self, container_id: str, env: dict[str, str]) -> tuple[int, float]:
        started = time.monotonic()
        try:
            result = _run(
                ["docker", "wait", container_id],
                env=env,
                check=False,
                timeout=SHUTDOWN_EXIT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise HarnessError("exporter did not exit within shutdown proof bound") from error
        try:
            return int(result.stdout.strip()), time.monotonic() - started
        except ValueError as error:
            raise HarnessError("docker wait did not return an exporter exit code") from error

    def _container_logs(self, container_id: str, env: dict[str, str]) -> str:
        return _run(
            ["docker", "logs", container_id],
            env=env,
            check=False,
            timeout=COMPOSE_TEARDOWN_TIMEOUT_SECONDS,
        ).stdout

    def _build_images(self) -> tuple[str, str]:
        """Build and resolve the locally pinned exporter and replay-origin images."""
        if self.build_exporter:
            _run(["docker", "build", "--load", "--tag", self.exporter_image, "."])
        exporter_id = image_id(self.exporter_image)
        proxy_tag = "failure-harness-proxy:local"
        _run([
            "docker",
            "build",
            "--pull=false",
            "--build-arg",
            f"EXPORTER_IMAGE={self.exporter_image}",
            "--build-arg",
            f"EXPORTER_IMAGE_ID={exporter_id}",
            "--tag",
            proxy_tag,
            "-f",
            str(PROXY_DOCKERFILE),
            ".",
        ])
        proxy_id = image_id(proxy_tag)
        recorded_base = image_label(proxy_tag, "io.m7kni.failure-harness.base-image-id")
        if recorded_base != exporter_id:
            raise HarnessError("proxy image does not record the resolved exporter image ID")
        return exporter_id, proxy_id

    def _write_duration_observation(self, observation: dict[str, object]) -> None:
        """Write redacted duration evidence, including the raw exporter responses."""
        (self.artifacts / "duration-observation.json").write_text(
            _redact(json.dumps(observation, indent=2, sort_keys=True)) + "\n", encoding="utf-8"
        )

    def _wait_for_duration_baseline(
        self,
        command: list[str],
        env: dict[str, str],
        runtime: Path,
        expected_paths: set[str],
    ) -> dict[str, object]:
        """Wait for a completed, stable baseline replay before observing the next wrapper."""
        deadline = time.monotonic() + DURATION_OBSERVATION_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                first = self._capture_duration_snapshot(command, env)
            except HarnessError:
                # The web process becomes probeable before the first collector
                # has necessarily emitted its labelled histogram child.
                time.sleep(0.25)
                continue
            journal = (runtime / "journal.jsonl").read_text(encoding="utf-8")
            logs_first = _duration_logs(command, env)
            if (
                _status_from_snapshot(first)["is_running"]
                or not _baseline_fixture_evidence(journal, expected_paths)
                or not _baseline_cache_evidence(_parse_json_logs(logs_first.splitlines()))
                or not _product_metric_evidence(first["metrics_raw"])
            ):
                time.sleep(0.25)
                continue
            time.sleep(0.25)
            second = self._capture_duration_snapshot(command, env)
            logs_second = _duration_logs(command, env)
            if _status_from_snapshot(second)["is_running"]:
                continue
            if (
                first["histogram"] == second["histogram"]
                and first["status"] == second["status"]
                and first["scheduler"] == second["scheduler"]
                and len(journal.splitlines())
                == len((runtime / "journal.jsonl").read_text(encoding="utf-8").splitlines())
                and len(_parse_json_logs(logs_first.splitlines()))
                == len(_parse_json_logs(logs_second.splitlines()))
            ):
                return second
        raise HarnessError("DeviceCollector did not reach a stable idle baseline within 90 seconds")

    def _wait_for_duration_completion(
        self,
        command: list[str],
        env: dict[str, str],
        pre: dict[str, object],
        observation_started_at: float,
    ) -> tuple[dict[str, object], float]:
        """Wait for the next scheduled wrapper run without altering its endpoint gates."""
        deadline = observation_started_at + DURATION_OBSERVATION_TIMEOUT_SECONDS
        pre_histogram = _histogram_from_snapshot(pre)
        while time.monotonic() < deadline:
            post = self._capture_duration_snapshot(command, env)
            elapsed = time.monotonic() - observation_started_at
            post_histogram = _histogram_from_snapshot(post)
            if post_histogram["count"] == pre_histogram["count"]:
                time.sleep(0.25)
                continue
            if _status_from_snapshot(post)["is_running"]:
                time.sleep(0.25)
                continue
            return post, elapsed
        raise HarnessError("scheduled DeviceCollector wrapper did not complete within 90 seconds")

    def _capture_duration_snapshot(
        self, command: list[str], env: dict[str, str]
    ) -> dict[str, object]:
        """Capture raw metrics/status responses and their DeviceCollector values."""
        snapshot_script = (
            "import json,os,httpx;"
            "headers={'Authorization':'Bearer '+os.environ['MERAKI_EXPORTER_SERVER__API_TOKEN']};"
            "m=httpx.get('http://127.0.0.1:9099/metrics',timeout=5);"
            "s=httpx.get('http://127.0.0.1:9099/status?format=json',headers=headers,timeout=5);"
            "print(json.dumps({'metrics_status':m.status_code,'metrics_raw':m.text,"
            "'status_status':s.status_code,'status_raw':s.text}))"
        )
        result = _run(
            [*command, "exec", "--no-TTY", "exporter", "python", "-c", snapshot_script], env=env
        )
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise HarnessError("duration snapshot returned invalid JSON output") from error
        if not isinstance(value, dict):
            raise HarnessError("duration snapshot output was not an object")
        metrics_raw = value.get("metrics_raw")
        status_raw = value.get("status_raw")
        if value.get("metrics_status") != 200 or not isinstance(metrics_raw, str):
            raise HarnessError("duration snapshot metrics request failed")
        if value.get("status_status") != 200 or not isinstance(status_raw, str):
            raise HarnessError("duration snapshot status request failed")
        try:
            status_payload = json.loads(status_raw)
        except json.JSONDecodeError as error:
            raise HarnessError("duration snapshot status response was not JSON") from error
        return {
            "monotonic_seconds": time.monotonic(),
            "metrics_raw": metrics_raw,
            "status_raw": status_raw,
            "histogram": _histogram_values(metrics_raw),
            "status": _device_collector_status(status_payload),
            "scheduler": _device_availability_scheduler(status_payload),
        }

    def _write_evidence(self, evidence: list[dict[str, object]]) -> None:
        """Persist completed and partial mode summaries as each mode terminates."""
        (self.artifacts / "evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _run_mode(
        self,
        mode: FaultMode,
        exporter_id: str,
        proxy_id: str,
        fixture_count: int,
        expected_paths: set[str],
    ) -> dict[str, object]:
        with tempfile.TemporaryDirectory(prefix="failure-harness-") as temporary:
            runtime = Path(temporary)
            corpus_dir = runtime / "corpus"
            shutil.copytree(self.manifest.parent, corpus_dir)
            create_tls_material(runtime)
            (runtime / "journal.jsonl").touch(mode=0o666)
            project = f"failure-harness-{mode.value}-{int(time.time() * 1000)}"
            decision = fault_decision(mode)
            env = {
                "HARNESS_IMAGE_ID": exporter_id,
                "HARNESS_PROXY_IMAGE_ID": proxy_id,
                "HARNESS_RUNTIME_DIR": str(runtime),
                "HARNESS_MODE": mode.value,
                "HARNESS_TARGET_OPERATION": self.target_operation or "",
                "HARNESS_ORIGIN_HOST": decision.origin_host,
                "HARNESS_TRUSTED_CA": "alternate-ca.pem"
                if mode == FaultMode.TLS_FAILURE
                else "trusted-ca.pem",
            }
            plan = {
                "mode": mode.value,
                "exporter_image_id": exporter_id,
                "proxy_image_id": proxy_id,
                "fixture_count": fixture_count,
                "target_operation": self.target_operation,
                "decision": decision.evidence,
            }
            (self.artifacts / f"run-plan-{mode.value}.json").write_text(
                json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            command = [
                "docker",
                "compose",
                "--project-name",
                project,
                "--env-file",
                "/dev/null",
                "-f",
                str(COMPOSE_FILE),
            ]
            probe: dict[str, int | str] | None = None
            teardown: dict[str, object] = {"fallback_required": False}
            result: dict[str, object] | None = None
            self._last_teardown_fallback = False
            try:
                _run([*command, "up", "--detach", "--no-build"], env=env)
                probe = self._probe_exporter(command, env)
                journal, logs, observation_seconds = self._wait_for_observation(
                    command, env, runtime, mode, expected_paths
                )
                self._write_mode_artifacts(mode, journal, logs, probe)
                result = {
                    "mode": mode.value,
                    "decision": decision.evidence,
                    "probe": probe,
                    "journal_entries": len(journal.splitlines()),
                    "observed": True,
                    "observation_seconds": round(observation_seconds, 3),
                }
            except Exception:
                failure_logs = _run([*command, "logs", "--no-color"], env=env, check=False).stdout
                failure_journal = (runtime / "journal.jsonl").read_text(encoding="utf-8")
                self._write_mode_artifacts(mode, failure_journal, failure_logs, probe)
                raise
            finally:
                try:
                    self._teardown(command, env, project, teardown)
                finally:
                    self._last_teardown_fallback = bool(teardown["fallback_required"])
                    self._write_teardown_artifact(mode, teardown)
            if result is None:
                raise HarnessError(f"mode {mode.value!r} did not produce a result")
            result["teardown_fallback"] = teardown["fallback_required"]
            return result

    def _teardown(
        self,
        command: list[str],
        env: dict[str, str],
        project: str,
        report: dict[str, object],
    ) -> None:
        """Stop Compose within a fixed bound, then remove only its labelled leftovers."""
        try:
            down_result = _run(
                [*command, "down", "--volumes"],
                env=env,
                check=False,
                timeout=COMPOSE_TEARDOWN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            self._run_project_cleanup_fallback(project, env, report, "compose_timeout")
            return

        if getattr(down_result, "returncode", 0) != 0:
            self._run_project_cleanup_fallback(project, env, report, "compose_nonzero")
            return

        try:
            remaining_containers = self._project_resource_ids("ps", project, env)
            remaining_networks = self._project_resource_ids("network", project, env)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            report["outcome"] = "verification_failed"
            raise HarnessError(
                "Compose teardown could not inspect exact-project resources"
            ) from error
        if remaining_containers or remaining_networks:
            self._run_project_cleanup_fallback(project, env, report, "resources_remaining")
            return
        report["outcome"] = "clean"

    def _run_project_cleanup_fallback(
        self,
        project: str,
        env: dict[str, str],
        report: dict[str, object],
        reason: str,
    ) -> None:
        """Run and record the bounded exact-project cleanup fallback."""
        report["fallback_required"] = True
        report["fallback_reason"] = reason
        try:
            self._force_cleanup_project_resources(project, env, report)
        except HarnessError:
            report["outcome"] = "fallback_failed"
            raise
        report["outcome"] = "fallback_cleaned"

    def _force_cleanup_project_resources(
        self, project: str, env: dict[str, str], report: dict[str, object]
    ) -> None:
        """Remove containers and networks selected by the exact Compose project label."""
        try:
            containers = self._project_resource_ids("ps", project, env)
            for container in containers:
                _run(
                    ["docker", "rm", "--force", container],
                    env=env,
                    check=False,
                    timeout=COMPOSE_TEARDOWN_TIMEOUT_SECONDS,
                )
            networks = self._project_resource_ids("network", project, env)
            for network in networks:
                _run(
                    ["docker", "network", "rm", network],
                    env=env,
                    check=False,
                    timeout=COMPOSE_TEARDOWN_TIMEOUT_SECONDS,
                )
            remaining_containers = self._project_resource_ids("ps", project, env)
            remaining_networks = self._project_resource_ids("network", project, env)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            report["fallback_error"] = type(error).__name__
            raise HarnessError(
                "exact-project cleanup could not inspect exact-project resources"
            ) from error

        report["containers_removed"] = len(containers)
        report["networks_removed"] = len(networks)
        if remaining_containers or remaining_networks:
            report["remaining_containers"] = len(remaining_containers)
            report["remaining_networks"] = len(remaining_networks)
            raise HarnessError("exact-project cleanup left exact-project resources behind")

    def _project_resource_ids(
        self,
        resource: str,
        project: str,
        env: dict[str, str],
    ) -> list[str]:
        """List only resources bearing this exact Compose project label."""
        command = ["docker", resource, "ls" if resource == "network" else "--all", "--quiet"]
        command.extend(["--filter", f"label=com.docker.compose.project={project}"])
        return [
            resource_id
            for resource_id in _run(
                command,
                env=env,
                timeout=COMPOSE_TEARDOWN_TIMEOUT_SECONDS,
            ).stdout.splitlines()
            if resource_id
        ]

    def _write_mode_artifacts(
        self, mode: FaultMode, journal: str, logs: str, probe: dict[str, int | str] | None
    ) -> None:
        """Retain redacted per-mode diagnostics regardless of success or failure."""
        (self.artifacts / f"compose-{mode.value}.log").write_text(_redact(logs), encoding="utf-8")
        (self.artifacts / f"journal-{mode.value}.jsonl").write_text(
            _redact(journal), encoding="utf-8"
        )
        if probe is not None:
            (self.artifacts / f"probe-{mode.value}.json").write_text(
                _redact(json.dumps(probe, indent=2, sort_keys=True)) + "\n", encoding="utf-8"
            )

    def _write_teardown_artifact(self, mode: FaultMode, teardown: dict[str, object]) -> None:
        """Persist redacted teardown outcome even when fallback cleanup fails."""
        (self.artifacts / f"teardown-{mode.value}.json").write_text(
            _redact(json.dumps(teardown, indent=2, sort_keys=True)) + "\n", encoding="utf-8"
        )

    def _probe_exporter(self, command: list[str], env: dict[str, str]) -> dict[str, int | str]:
        deadline = time.monotonic() + 30
        last_error: Exception | None = None
        probe_script = (
            "import json,httpx;"
            "h=httpx.get('http://127.0.0.1:9099/health',timeout=5);"
            "m=httpx.get('http://127.0.0.1:9099/metrics',timeout=5);"
            "print(json.dumps({'health':h.status_code,'metrics':m.status_code,"
            "'metrics_body':m.text}))"
        )
        while time.monotonic() < deadline:
            try:
                result = _run(
                    [*command, "exec", "--no-TTY", "exporter", "python", "-c", probe_script],
                    env=env,
                )
                value = json.loads(result.stdout)
                if isinstance(value, dict):
                    return value
            except (json.JSONDecodeError, subprocess.CalledProcessError) as error:
                last_error = error
                time.sleep(0.25)
        raise HarnessError("exporter did not become probeable within 30 seconds") from last_error

    def _wait_for_observation(
        self,
        command: list[str],
        env: dict[str, str],
        runtime: Path,
        mode: FaultMode,
        expected_paths: set[str],
    ) -> tuple[str, str, float]:
        started = time.monotonic()
        deadline = started + 40
        journal = ""
        logs = ""
        while time.monotonic() < deadline:
            journal = (runtime / "journal.jsonl").read_text(encoding="utf-8")
            logs = _run([*command, "logs", "--no-color"], env=env).stdout
            elapsed = time.monotonic() - started
            if _mode_observed(mode, journal, logs, expected_paths, elapsed=elapsed):
                return journal, logs, elapsed
            time.sleep(0.25)
        raise HarnessError(f"mode {mode.value!r} produced no expected evidence within 40 seconds")


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    import os

    merged_env = os.environ | (env or {})
    return subprocess.run(
        command,
        check=check,
        text=True,
        capture_output=True,
        env=merged_env,
        timeout=timeout,
    )


def _redact(value: str) -> str:
    return value.replace("harness-sentinel-not-a-secret", "[REDACTED]").replace(
        DURATION_OBSERVATION_CONTROL_TOKEN, "[REDACTED]"
    )


def _histogram_values(metrics_raw: str) -> dict[str, float]:
    """Extract the DeviceCollector duration histogram sum and count from Prometheus text."""
    values: dict[str, float] = {}
    for suffix in ("sum", "count"):
        pattern = re.compile(
            rf"^{re.escape(_DURATION_METRIC)}_{suffix}"
            r'\{[^\n}]*collector="DeviceCollector"[^\n}]*\}\s+([^\s]+)$',
            re.MULTILINE,
        )
        match = pattern.search(metrics_raw)
        if match is None:
            raise HarnessError(f"DeviceCollector duration histogram {suffix} was absent")
        try:
            values[suffix] = float(match.group(1))
        except ValueError as error:
            raise HarnessError(
                f"DeviceCollector duration histogram {suffix} was not numeric"
            ) from error
    if values["count"] < 0 or values["sum"] < 0:
        raise HarnessError("DeviceCollector duration histogram cannot be negative")
    return values


def _device_collector_status(status_payload: object) -> dict[str, int | float | bool]:
    """Return precisely the status fields used to prove one scheduled collector run."""
    if not isinstance(status_payload, dict):
        raise HarnessError("status response was not an object")
    collectors = status_payload.get("collectors")
    if not isinstance(collectors, list):
        raise HarnessError("status response did not contain collectors")
    for collector in collectors:
        if not isinstance(collector, dict) or collector.get("name") != "DeviceCollector":
            continue
        result: dict[str, int | float | bool] = {}
        for name in ("total_runs", "total_successes", "total_failures"):
            value = collector.get(name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise HarnessError(f"DeviceCollector status {name} was not an integer")
            result[name] = value
        is_running = collector.get("is_running")
        if not isinstance(is_running, bool):
            raise HarnessError("DeviceCollector status is_running was not a boolean")
        result["is_running"] = is_running
        last_success_time = collector.get("last_success_time")
        if not isinstance(last_success_time, (int, float)) or isinstance(last_success_time, bool):
            raise HarnessError("DeviceCollector status last_success_time was not numeric")
        result["last_success_time"] = float(last_success_time)
        return result
    raise HarnessError("status response did not contain DeviceCollector")


def _histogram_from_snapshot(snapshot: dict[str, object]) -> dict[str, float]:
    histogram = snapshot.get("histogram")
    if not isinstance(histogram, dict):
        raise HarnessError("duration snapshot did not contain a histogram")
    count = histogram.get("count")
    total = histogram.get("sum")
    if not isinstance(count, float) or not isinstance(total, float):
        raise HarnessError("duration snapshot histogram values were invalid")
    return {"count": count, "sum": total}


def _status_from_snapshot(snapshot: dict[str, object]) -> dict[str, int | float | bool]:
    status = snapshot.get("status")
    if not isinstance(status, dict):
        raise HarnessError("duration snapshot did not contain collector status")
    result: dict[str, int | float | bool] = {}
    for name in (
        "total_runs",
        "total_successes",
        "total_failures",
        "is_running",
        "last_success_time",
    ):
        value = status.get(name)
        if name == "is_running":
            if not isinstance(value, bool):
                raise HarnessError("duration snapshot is_running was invalid")
        elif name == "last_success_time":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise HarnessError("duration snapshot last_success_time was invalid")
            value = float(value)
        elif not isinstance(value, int) or isinstance(value, bool):
            raise HarnessError(f"duration snapshot {name} was invalid")
        result[name] = value
    return result


def _duration_observation(
    pre: dict[str, object],
    post: dict[str, object],
    *,
    elapsed_seconds: float,
    observation_window: tuple[float, float] | None = None,
) -> dict[str, object]:
    """Calculate and enforce the fixed single-run duration-observation contract."""
    if elapsed_seconds <= 0:
        raise HarnessError("observation elapsed time must be positive")
    pre_histogram = _histogram_from_snapshot(pre)
    post_histogram = _histogram_from_snapshot(post)
    pre_status = _status_from_snapshot(pre)
    post_status = _status_from_snapshot(post)
    if bool(post_status["is_running"]):
        raise HarnessError("DeviceCollector must be idle after the observed wrapper")

    count_delta = post_histogram["count"] - pre_histogram["count"]
    sum_delta = post_histogram["sum"] - pre_histogram["sum"]
    run_delta = int(post_status["total_runs"]) - int(pre_status["total_runs"])
    success_delta = int(post_status["total_successes"]) - int(pre_status["total_successes"])
    failure_delta = int(post_status["total_failures"]) - int(pre_status["total_failures"])
    if count_delta != 1:
        raise HarnessError("duration histogram count delta must equal 1")
    if run_delta != 1:
        raise HarnessError("total_runs delta must equal 1")
    if success_delta != 1:
        raise HarnessError("total_successes delta must equal 1")
    if failure_delta != 0:
        raise HarnessError("total_failures delta must equal 0")
    if sum_delta <= 0:
        raise HarnessError("duration histogram sum delta must be positive")
    mean = sum_delta / count_delta
    if not 0 < mean <= elapsed_seconds:
        raise HarnessError(
            "duration mean must be positive and no greater than observation elapsed time"
        )
    pre_success = float(pre_status["last_success_time"])
    post_success = float(post_status["last_success_time"])
    if post_success <= pre_success:
        raise HarnessError("last_success_time must advance after the observed wrapper")
    pre_scheduler = _scheduler_from_snapshot(pre)
    post_scheduler = _scheduler_from_snapshot(post)
    if post_scheduler["attempts"] != pre_scheduler["attempts"]:
        raise HarnessError("device_availability scheduler attempts changed during wrapper-only run")
    if (
        post_scheduler["last_success_timestamp_seconds"]
        != pre_scheduler["last_success_timestamp_seconds"]
    ):
        raise HarnessError("device_availability scheduler success changed during wrapper-only run")
    if observation_window is not None:
        started, finished = observation_window
        if not started <= post_success <= finished:
            raise HarnessError("last_success_time must fall within the observation window")
    return {
        "acceptance": "passed",
        "observation_elapsed_seconds": elapsed_seconds,
        "deltas": {
            "histogram_count": int(count_delta),
            "histogram_sum_seconds": sum_delta,
            "mean_seconds": mean,
            "total_runs": run_delta,
            "total_successes": success_delta,
            "total_failures": failure_delta,
            "last_success_time_seconds": post_success - pre_success,
        },
    }


def _has_verified_paths(journal: str, expected_paths: set[str]) -> bool:
    """Check that all fixed corpus paths have a verified fixture match."""
    return _baseline_fixture_evidence(journal, expected_paths)


def _post_boundary_verified_paths(
    journal: str, boundary: int, expected_paths: set[str]
) -> set[str]:
    """Reject all upstream requests after the observation boundary.

    A warmed inventory must satisfy the observed scheduler wrapper entirely from cache;
    the old requirement to replay every route after the boundary was impossible.
    """
    suffix = journal.splitlines()[boundary:]
    if suffix:
        raise HarnessError("upstream request recorded after duration observation boundary")
    if not expected_paths:
        return set()
    # Retained only for callers that explicitly need pre-boundary fixture proof.
    matched: set[str] = set()
    for line in journal.splitlines()[:boundary]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if (
            isinstance(path, str)
            and entry.get("reason") == "matched"
            and entry.get("evidence") == "verified fixture"
        ):
            matched.add(path)
    missing = expected_paths - matched
    if missing:
        raise HarnessError(
            f"missing verified fixture matches before observation: {sorted(missing)}"
        )
    return matched & expected_paths


def _duration_logs(command: list[str], env: dict[str, str], *, check: bool = True) -> str:
    """Read only exporter JSON logs; Compose itself remains outside the proof."""
    return _run(
        [*command, "logs", "--no-color", "--no-log-prefix", "exporter"], env=env, check=check
    ).stdout


def _parse_json_logs(lines: list[str]) -> list[dict[str, object]]:
    """Parse JSON structured exporter logs, ignoring non-JSON runtime noise."""
    parsed: list[dict[str, object]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed


def _baseline_fixture_evidence(journal: str, expected_paths: set[str]) -> bool:
    """Require matched verified fixtures and a separate HTTP 200 response for each route."""
    entries = _journal_entries(journal)
    matched = {
        str(entry["path"])
        for entry in entries
        if entry.get("reason") == "matched"
        and entry.get("evidence") == "verified fixture"
        and isinstance(entry.get("path"), str)
    }
    responded = {
        str(entry["path"])
        for entry in entries
        if entry.get("reason") == "response:sent"
        and entry.get("evidence") == "HTTP 200 response sent"
        and isinstance(entry.get("path"), str)
    }
    return expected_paths <= matched and expected_paths <= responded


def _journal_entries(journal: str) -> list[dict[str, object]]:
    return _parse_json_logs(journal.splitlines())


def _baseline_cache_evidence(logs: list[dict[str, object]]) -> bool:
    """Require each warmed cache to contain data before the observation boundary."""
    required = {
        "Updated organization cache": "org_count",
        "Updated network cache": "network_count",
        "Updated device cache": "device_count",
        "Updated device availabilities cache": "device_count",
    }
    for event, count_name in required.items():
        if not any(
            entry.get("event") == event and _positive_count(entry, count_name) for entry in logs
        ):
            return False
    return True


def _post_boundary_cache_lineage(logs: list[dict[str, object]]) -> None:
    """Prove the scheduled wrapper used warm inventory without a due endpoint group."""
    required = {
        "Cache hit for organizations",
        "Cache hit for networks",
        "Cache hit for devices",
    }
    hits = {str(entry.get("event")) for entry in logs if entry.get("event") in required}
    if hits != required:
        raise HarnessError(f"missing post-boundary cache hits: {sorted(required - hits)}")
    for entry in logs:
        event = entry.get("event")
        if event in required:
            age = entry.get("cache_age_seconds")
            if (
                not isinstance(age, (int, float))
                or isinstance(age, bool)
                or not math.isfinite(age)
                or age < 0
            ):
                raise HarnessError("post-boundary cache hit had invalid cache_age_seconds")
        if isinstance(event, str) and (
            event.startswith("Cache miss")
            or "cache update" in event.lower()
            or "cache invalidat" in event.lower()
        ):
            raise HarnessError(f"post-boundary cache mutation observed: {event}")


def _processing_evidence(logs: list[dict[str, object]]) -> None:
    """Require non-empty cached processing while the availability endpoint remains gated."""
    has_orgs = any(_positive_count(entry, "org_count") for entry in logs)
    if not has_orgs:
        raise HarnessError("scheduled DeviceCollector processing evidence had no organizations")
    for entry in logs:
        if entry.get("event") != "Processing devices":
            continue
        if (
            _positive_count(entry, "device_count")
            and entry.get("availability_count") == 0
            and entry.get("availability_due") is False
        ):
            return
    raise HarnessError("scheduled DeviceCollector processing evidence was absent or empty")


def _positive_count(entry: dict[str, object], name: str) -> bool:
    value = entry.get(name)
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _device_availability_scheduler(status_payload: object) -> dict[str, int | float]:
    """Return the device_availability scheduler lineage exposed by /status."""
    if not isinstance(status_payload, dict):
        raise HarnessError("status response was not an object")
    scheduler = status_payload.get("scheduler")
    if not isinstance(scheduler, dict) or not isinstance(scheduler.get("groups"), list):
        raise HarnessError("status response did not contain scheduler groups")
    for group in scheduler["groups"]:
        if not isinstance(group, dict) or group.get("name") != "device_availability":
            continue
        attempts = group.get("attempts")
        success = group.get("last_success_timestamp_seconds")
        if not isinstance(attempts, int) or isinstance(attempts, bool):
            raise HarnessError("device_availability scheduler attempts were invalid")
        if not isinstance(success, (int, float)) or isinstance(success, bool):
            raise HarnessError("device_availability scheduler success timestamp was invalid")
        return {"attempts": attempts, "last_success_timestamp_seconds": float(success)}
    raise HarnessError("status response did not contain device_availability scheduler group")


def _scheduler_from_snapshot(snapshot: dict[str, object]) -> dict[str, int | float]:
    scheduler = snapshot.get("scheduler")
    if not isinstance(scheduler, dict):
        raise HarnessError("duration snapshot did not contain scheduler lineage")
    attempts = scheduler.get("attempts")
    success = scheduler.get("last_success_timestamp_seconds")
    if not isinstance(attempts, int) or isinstance(attempts, bool):
        raise HarnessError("duration snapshot scheduler attempts were invalid")
    if not isinstance(success, float):
        raise HarnessError("duration snapshot scheduler success timestamp was invalid")
    return {"attempts": attempts, "last_success_timestamp_seconds": success}


def _product_metric_evidence(metrics_raw: object) -> list[str]:
    """Keep one corpus-backed device product series as baseline evidence."""
    if not isinstance(metrics_raw, str):
        return []
    return [
        line
        for line in metrics_raw.splitlines()
        if line.startswith((
            "meraki_device_",
            "meraki_mr_",
            "meraki_ms_",
            "meraki_mx_",
            "meraki_mt_",
            "meraki_mg_",
            "meraki_mv_",
        ))
        and not line.startswith("#")
    ][:10]


def _manifest_provenance(manifest: Path, corpus: object) -> dict[str, object]:
    """Retain the manifest's verified immutable provenance without fixture bodies."""
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HarnessError("could not retain duration manifest provenance") from error
    rows = raw.get("fixtures") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise HarnessError("duration manifest provenance did not contain fixtures")
    fixtures = getattr(corpus, "fixtures", ())
    return {
        "manifest_schema_version": raw.get("schema_version"),
        "fixture_count": len(fixtures),
        "fixtures": [
            {
                "fixture": row.get("fixture"),
                "path": row.get("path"),
                "sha256": row.get("sha256"),
                "evidence_status": row.get("evidence_status"),
                "evidence_source": row.get("evidence_source"),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _barrier_order(
    entries: list[dict[str, object]],
    *,
    term_monotonic_seconds: float,
    target_path: str | None = None,
    term_journal_boundary: int | None = None,
) -> dict[str, object]:
    """Require the blocked request, TERM, and independent release in causal order."""
    relevant = [
        entry for entry in entries if target_path is None or entry.get("path") == target_path
    ]
    entered_index = next(
        (
            index
            for index, entry in enumerate(entries)
            if (target_path is None or entry.get("path") == target_path)
            and entry.get("reason") == "barrier:entered"
        ),
        None,
    )
    released_index = next(
        (
            index
            for index, entry in enumerate(entries)
            if (target_path is None or entry.get("path") == target_path)
            and entry.get("reason") == "barrier:released"
        ),
        None,
    )
    entered = next(
        (
            entry.get("monotonic_seconds")
            for entry in relevant
            if entry.get("reason") == "barrier:entered"
        ),
        None,
    )
    released = next(
        (
            entry.get("monotonic_seconds")
            for entry in relevant
            if entry.get("reason") == "barrier:released"
        ),
        None,
    )
    if not isinstance(entered, (int, float)) or not isinstance(released, (int, float)):
        raise HarnessError(
            "shutdown proof requires barrier:entered and barrier:released journal markers"
        )
    entered_value, released_value = float(entered), float(released)
    if term_journal_boundary is not None:
        if not isinstance(entered_index, int) or not isinstance(released_index, int):
            raise HarnessError("shutdown proof could not locate barrier journal positions")
        if not entered_index < term_journal_boundary <= released_index:
            raise HarnessError("shutdown proof requires request:entered < TERM < barrier:released")
    elif not entered_value < term_monotonic_seconds < released_value:
        raise HarnessError("shutdown proof requires request:entered < TERM < barrier:released")
    return {
        "causal_order": "barrier:entered < host TERM < barrier:released",
        "causal_basis": (
            "journal_line_boundary"
            if term_journal_boundary is not None
            else "shared_monotonic_test_clock"
        ),
        "entered_journal_index": entered_index,
        "term_journal_boundary": term_journal_boundary,
        "released_journal_index": released_index,
        # Origin and host clocks are retained independently, not compared across containers.
        "origin_entered_monotonic_seconds": entered_value,
        "host_term_monotonic_seconds": term_monotonic_seconds,
        "origin_released_monotonic_seconds": released_value,
    }


def _lifecycle_order(logs: list[dict[str, object]]) -> dict[str, object]:
    """Require the structured shutdown dependency order emitted by the exporter."""
    markers = [
        str(entry["phase"])
        if entry.get("event") == "Shutdown phase complete" and isinstance(entry.get("phase"), str)
        else "Shutdown complete"
        for entry in logs
        if entry.get("event") in {"Shutdown phase complete", "Shutdown complete"}
    ]
    required = [
        "otel_metrics_stopped",
        "dns_executor_drained",
        "sdk_executor_drained",
        "sdk_session_closed",
        "sdk_client_closed",
        "serving_executor_drained",
        "Shutdown complete",
    ]
    optional_order = ["tracing_stopped", "otel_logging_stopped", "data_log_stopped"]
    positions: dict[str, int] = {}
    for marker in required:
        if marker not in markers:
            raise HarnessError(f"shutdown lifecycle marker {marker!r} was absent")
        positions[marker] = markers.index(marker)
    for first, second in zip(required, required[1:], strict=False):
        if positions[first] >= positions[second]:
            raise HarnessError(f"shutdown lifecycle order requires {first} before {second}")
    observed_optional = [marker for marker in optional_order if marker in markers]
    optional_positions = [markers.index(marker) for marker in observed_optional]
    if optional_positions != sorted(optional_positions):
        raise HarnessError("optional OTel shutdown lifecycle markers were out of documented order")
    if any(
        markers.index(marker) > positions["dns_executor_drained"] for marker in observed_optional
    ):
        raise HarnessError("optional OTel shutdown lifecycle markers must precede DNS drain")
    return {"ordered_markers": markers, "required_positions": positions}


def _mode_observed(
    mode: FaultMode,
    journal: str,
    logs: str,
    expected_paths: set[str],
    *,
    elapsed: float,
) -> bool:
    """Require an externally retained decision before a mode can be reported as run."""
    entries: list[dict[str, object]] = []
    for line in journal.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            entries.append(value)
    if mode in {FaultMode.BASELINE, FaultMode.TRUSTED_TLS}:
        matched = {entry.get("path") for entry in entries if entry.get("reason") == "matched"}
        return expected_paths <= matched
    lowered_logs = logs.lower()
    if mode == FaultMode.TLS_FAILURE:
        return any(
            marker in lowered_logs
            for marker in ("certificate verify failed", "certificate_verify_failed")
        )
    if mode == FaultMode.DNS_FAILURE:
        return any(
            marker in lowered_logs
            for marker in (
                "name resolution",
                "failed to resolve",
                "nodename nor servname",
            )
        )
    reasons = {entry.get("reason") for entry in entries}
    if mode == FaultMode.TIMEOUT:
        return "barrier:entered" in reasons and elapsed >= 10.5
    if mode == FaultMode.STALL:
        return "barrier:entered" in reasons and "barrier:held" in reasons
    if mode == FaultMode.SLOW_VALID:
        return (
            _has_ordered_events(
                entries,
                "fault:slow_valid",
                "matched",
                expected_paths,
                require_verified_fixture=True,
            )
            and elapsed >= 2
        )
    if mode == FaultMode.RESET:
        return _has_ordered_events(
            entries, "fault:reset", "transport:aborted", expected_paths
        ) and any(
            marker in lowered_logs
            for marker in (
                "connection reset by peer",
                "server disconnected without sending a response",
                "remoteprotocolerror",
            )
        )
    if mode in {FaultMode.RATE_LIMIT_SECONDS, FaultMode.RATE_LIMIT_HTTP_DATE}:
        return fault_decision(mode).reason in reasons and _has_retry_after(
            entries, mode, expected_paths
        )
    return fault_decision(mode).reason in reasons


def _has_ordered_events(
    entries: list[dict[str, object]],
    first_reason: str,
    second_reason: str,
    paths: set[str],
    *,
    require_verified_fixture: bool = False,
) -> bool:
    """Find causally ordered records for one replayed route."""
    for first_index, first in enumerate(entries):
        if first.get("reason") != first_reason or first.get("path") not in paths:
            continue
        for second in entries[first_index + 1 :]:
            if second.get("reason") != second_reason or second.get("path") != first.get("path"):
                continue
            if not require_verified_fixture or second.get("evidence") == "verified fixture":
                return True
    return False


def _has_retry_after(entries: list[dict[str, object]], mode: FaultMode, paths: set[str]) -> bool:
    """Require the exact header sent on the wire, including valid HTTP-date syntax."""
    for entry in entries:
        if entry.get("reason") != "response:sent" or entry.get("path") not in paths:
            continue
        headers = entry.get("headers")
        if not isinstance(headers, dict):
            continue
        retry_after = headers.get("Retry-After")
        if not isinstance(retry_after, str):
            continue
        if mode == FaultMode.RATE_LIMIT_SECONDS:
            return retry_after == "2"
        try:
            parsed = parsedate_to_datetime(retry_after)
        except TypeError, ValueError:
            continue
        if parsed.tzinfo is not None and retry_after.endswith(" GMT"):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--artifacts", type=Path, default=Path(".failure-harness-artifacts"))
    parser.add_argument("--exporter-image", default="meraki-dashboard-exporter:failure-harness")
    parser.add_argument("--build-exporter", action="store_true")
    parser.add_argument("--target-operation")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate-corpus")
    commands.add_parser("observe-duration")
    commands.add_parser("observe-shutdown")
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--mode", choices=[mode.value for mode in FaultMode])
    run_parser.add_argument("--all-modes", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "validate-corpus":
            print(
                f"validated {len(load_manifest(args.manifest, require_real=True).fixtures)} fixture(s)"
            )
            return 0
        if args.command == "observe-duration":
            HarnessRunner(
                args.manifest,
                args.artifacts,
                exporter_image=args.exporter_image,
                build_exporter=args.build_exporter,
            ).observe_duration()
            return 0
        if args.command == "observe-shutdown":
            HarnessRunner(
                args.manifest,
                args.artifacts,
                exporter_image=args.exporter_image,
                build_exporter=args.build_exporter,
                target_operation=args.target_operation,
            ).observe_shutdown()
            return 0
        if not args.mode and not args.all_modes:
            parser.error("run requires --mode or --all-modes")
        modes = list(FaultMode) if args.all_modes else [FaultMode(args.mode)]
        HarnessRunner(
            args.manifest,
            args.artifacts,
            exporter_image=args.exporter_image,
            build_exporter=args.build_exporter,
            target_operation=args.target_operation,
        ).run(modes)
    except (CorpusError, HarnessError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
