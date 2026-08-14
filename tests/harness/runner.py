"""Executable, offline Docker Compose runner for the failure replay harness."""
# ruff: noqa: D102, D103, D107

from __future__ import annotations

import argparse
import json
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
    return value.replace("harness-sentinel-not-a-secret", "[REDACTED]")


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
