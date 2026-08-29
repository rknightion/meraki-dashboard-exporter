"""Contracts for the offline failure-replay harness (#713)."""
# ruff: noqa: D103

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID

from tests.harness.corpus import REQUIRED_OPERATIONS, Corpus, CorpusError, Fixture, load_manifest
from tests.harness.runner import HarnessError, HarnessRunner, _mode_observed, image_id
from tests.harness.sanitizer import SanitizationError, sanitize_capture_set
from tests.harness.server import FaultMode, ReplayApplication, _close_writer, fault_decision
from tests.harness.tls import create_tls_material


def _manifest(tmp_path: Path, *, evidence_status: str = "LIVE-VERIFIED") -> Path:
    fixtures = {
        "getOrganization": ("organization.json", "/api/v1/organizations/org_001"),
        "getOrganizationNetworks": (
            "networks.json",
            "/api/v1/organizations/org_001/networks",
        ),
        "getOrganizationDevices": ("devices.json", "/api/v1/organizations/org_001/devices"),
        "getOrganizationDevicesAvailabilities": (
            "availabilities.json",
            "/api/v1/organizations/org_001/devices/availabilities",
        ),
    }
    manifest = {
        "schema_version": 1,
        "fixtures": [],
    }
    for operation, (name, path) in fixtures.items():
        payload_path = tmp_path / name
        payload_path.write_text('{"id":"org_001","name":"organization_001"}')
        manifest["fixtures"].append({
            "fixture": name,
            "sha256": hashlib.sha256(payload_path.read_bytes()).hexdigest(),
            "capture_date_utc": "2026-08-14",
            "product_family": "organizations",
            "method": "GET",
            "path": path,
            "sdk_operation": operation,
            "sanitizer": {
                "name": "failure-harness",
                "version": "2",
                "method": "operation-aware",
            },
            "evidence_source": "synthetic unit fixture",
            "evidence_status": evidence_status,
        })
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


def test_manifest_requires_live_provenance_and_matching_digest(tmp_path: Path) -> None:
    """Only digest-pinned, live-verified payloads can drive a real scenario."""
    manifest = _manifest(tmp_path)
    assert load_manifest(manifest, require_real=True).fixtures[0].path.endswith("org_001")
    _manifest(tmp_path, evidence_status="SHAPE-ASSUMED")
    with pytest.raises(CorpusError, match="LIVE-VERIFIED"):
        load_manifest(manifest, require_real=True)
    manifest = _manifest(tmp_path)
    (tmp_path / "organization.json").write_text("tampered")
    with pytest.raises(CorpusError, match="digest"):
        load_manifest(manifest, require_real=True)


def test_real_manifest_requires_the_exact_four_unique_operations_and_routes(
    tmp_path: Path,
) -> None:
    """The runnable corpus is a fixed, route-unique four-operation contract."""
    manifest = _manifest(tmp_path)
    data = json.loads(manifest.read_text())
    assert {row["sdk_operation"] for row in data["fixtures"]} == REQUIRED_OPERATIONS

    data["fixtures"].pop()
    manifest.write_text(json.dumps(data))
    with pytest.raises(CorpusError, match="required operations"):
        load_manifest(manifest, require_real=True)

    manifest = _manifest(tmp_path)
    data = json.loads(manifest.read_text())
    data["fixtures"][-1]["sdk_operation"] = "getOrganization"
    manifest.write_text(json.dumps(data))
    with pytest.raises(CorpusError, match="duplicate sdk_operation"):
        load_manifest(manifest, require_real=True)

    manifest = _manifest(tmp_path)
    data = json.loads(manifest.read_text())
    data["fixtures"][-1].update({
        field: data["fixtures"][0][field]
        for field in ("method", "path", "query")
        if field in data["fixtures"][0]
    })
    manifest.write_text(json.dumps(data))
    with pytest.raises(CorpusError, match="duplicate method/path/query route"):
        load_manifest(manifest, require_real=True)


def test_sanitizer_shares_operation_aware_references_and_replaces_embedded_values() -> None:
    """Four synthetic shapes retain joins without retaining raw identifying values."""
    captures = {
        "getOrganization": {
            "id": "123",
            "name": "HQ",
            "url": "https://private.example",
            "status": "10.0.0.1 / 00:11:22:33:44:55",
        },
        "getOrganizationNetworks": [{"id": "N_1", "organizationId": "123", "name": "HQ LAN"}],
        "getOrganizationDevices": [{"serial": "Q2XX-AAAA-BBBB", "networkId": "N_1", "name": "AP"}],
        "getOrganizationDevicesAvailabilities": [
            {
                "serial": "Q2XX-AAAA-BBBB",
                "network": {"id": "N_1"},
                "alertProfileIds": [676102894059091620],
            }
        ],
        "getNetwork": {
            "id": "N_1",
            "name": "HQ LAN",
            "ipv6": "2001:4860::1",
            "mac": "00:11:22:33:44:55",
            "lat": 51.5072,
            "lng": -0.1276,
            "productTypes": ["wireless", "switch"],
        },
    }
    sanitized = sanitize_capture_set(captures)
    organization = cast(dict[str, str], sanitized["getOrganization"])
    networks = cast(list[dict[str, str]], sanitized["getOrganizationNetworks"])
    devices = cast(list[dict[str, str]], sanitized["getOrganizationDevices"])
    availabilities = cast(
        list[dict[str, object]], sanitized["getOrganizationDevicesAvailabilities"]
    )
    network = cast(dict[str, str], sanitized["getNetwork"])
    assert organization["id"] == "org_001"
    assert networks[0]["organizationId"] == "org_001"
    assert networks[0]["id"] == "network_001"
    assert network["id"] == "network_001"
    assert devices[0]["networkId"] == "network_001"
    assert devices[0]["serial"] == "device_001"
    assert cast(dict[str, str], availabilities[0]["network"])["id"] == "network_001"
    assert availabilities[0]["serial"] == "device_001"
    numeric_ids = cast(list[int], availabilities[0]["alertProfileIds"])
    assert numeric_ids != [676102894059091620]
    assert all(isinstance(value, int) for value in numeric_ids)
    assert organization["url"] == "url_value_001"
    assert "02:00:00:00:00:01" in organization["status"]
    assert "192.0.2.1" in organization["status"]
    assert "2001:db8::1" in network["ipv6"]
    assert network["mac"] == "02:00:00:00:00:01"
    assert network["lat"] == 0.0
    assert network["lng"] == 0.0
    assert network["productTypes"] == ["wireless", "switch"]
    assert "10.0.0.1" not in json.dumps(sanitized)


def test_sanitizer_rejects_credentials() -> None:
    with pytest.raises(SanitizationError, match="credential"):
        sanitize_capture_set({"getOrganization": {"X-Cisco-Meraki-API-Key": "secret"}})


def test_sanitizer_requires_the_refresh_contract_operations() -> None:
    with pytest.raises(SanitizationError, match="missing required operations"):
        sanitize_capture_set({"getOrganization": {"id": "123"}})


def test_every_fault_has_an_externally_checkable_decision(tmp_path: Path) -> None:
    corpus = load_manifest(_manifest(tmp_path), require_real=True)
    app = ReplayApplication(corpus, mode=FaultMode.BASELINE)
    assert app.route("GET", "/api/v1/organizations/org_001", "")[0] == 200
    assert app.route("POST", "/api/v1/organizations/org_001", "")[0] == 404
    assert app.journal[-1].reason == "unexpected_request"
    assert {mode.value for mode in FaultMode} == {
        "baseline",
        "trusted_tls",
        "unauthorized",
        "forbidden",
        "rate_limit_seconds",
        "rate_limit_http_date",
        "timeout",
        "stall",
        "tls_failure",
        "html",
        "slow_valid",
        "reset",
        "dns_failure",
        "server_error",
    }
    for mode in FaultMode:
        decision = fault_decision(mode)
        assert decision.evidence and decision.reason.startswith("fault:")
    assert fault_decision(FaultMode.RESET).transport_reset is True
    assert fault_decision(FaultMode.HTML).status == 200
    assert fault_decision(FaultMode.TLS_FAILURE).origin_host == "replay-origin"
    assert fault_decision(FaultMode.DNS_FAILURE).origin_host == "unresolvable.invalid"
    assert fault_decision(FaultMode.SERVER_ERROR).status == 503


def test_runner_requires_external_evidence_for_each_mode() -> None:
    paths = {"/api/v1/organizations/org_001", "/api/v1/organizations/org_001/networks"}
    complete = "\n".join(json.dumps({"path": path, "reason": "matched"}) for path in sorted(paths))
    partial = json.dumps({"path": next(iter(paths)), "reason": "matched"})
    assert _mode_observed(FaultMode.BASELINE, complete, "", paths, elapsed=1)
    assert not _mode_observed(FaultMode.BASELINE, partial, "", paths, elapsed=1)
    assert _mode_observed(
        FaultMode.TLS_FAILURE,
        "",
        "certificate verify failed",
        paths,
        elapsed=1,
    )
    assert _mode_observed(
        FaultMode.DNS_FAILURE,
        "",
        "name resolution failed",
        paths,
        elapsed=1,
    )
    timeout_journal = json.dumps({"path": next(iter(paths)), "reason": "barrier:entered"})
    assert not _mode_observed(FaultMode.TIMEOUT, timeout_journal, "", paths, elapsed=9)
    assert _mode_observed(FaultMode.TIMEOUT, timeout_journal, "", paths, elapsed=11)
    assert _mode_observed(
        FaultMode.SERVER_ERROR,
        json.dumps({
            "path": "/api/v1/organizations/org_001/networks",
            "reason": "fault:server_error",
        }),
        "",
        paths,
        elapsed=1,
    )


def test_fault_gates_require_causal_evidence_not_proxy_intent() -> None:
    """Delayed, stalled, and reset responses need proof beyond a fault decision."""
    path = "/api/v1/organizations/org_001"
    slow_intent = json.dumps({"path": path, "reason": "fault:slow_valid"})
    assert not _mode_observed(FaultMode.SLOW_VALID, slow_intent, "", {path}, elapsed=2.1)
    slow_complete = "\n".join((
        slow_intent,
        json.dumps({"path": path, "reason": "matched", "evidence": "verified fixture"}),
    ))
    assert not _mode_observed(FaultMode.SLOW_VALID, slow_complete, "", {path}, elapsed=1.9)
    assert _mode_observed(FaultMode.SLOW_VALID, slow_complete, "", {path}, elapsed=2.0)

    stall_entered = json.dumps({"path": path, "reason": "barrier:entered"})
    assert not _mode_observed(FaultMode.STALL, stall_entered, "", {path}, elapsed=1)
    stalled = "\n".join((stall_entered, json.dumps({"path": path, "reason": "barrier:held"})))
    assert _mode_observed(FaultMode.STALL, stalled, "", {path}, elapsed=1)

    reset_intent = json.dumps({"path": path, "reason": "fault:reset"})
    reset_abort = json.dumps({"path": path, "reason": "transport:aborted"})
    assert not _mode_observed(
        FaultMode.RESET, reset_intent, "connection reset by peer", {path}, elapsed=1
    )
    assert not _mode_observed(
        FaultMode.RESET,
        "\n".join((reset_abort, reset_intent)),
        "connection reset by peer",
        {path},
        elapsed=1,
    )
    assert not _mode_observed(
        FaultMode.RESET, "\n".join((reset_intent, reset_abort)), "", {path}, elapsed=1
    )
    assert _mode_observed(
        FaultMode.RESET,
        "\n".join((reset_intent, reset_abort)),
        "connection reset by peer",
        {path},
        elapsed=1,
    )


def test_rate_limit_gates_require_the_emitted_retry_after_shape() -> None:
    path = "/api/v1/organizations/org_001"
    seconds = "\n".join((
        json.dumps({"path": path, "reason": "fault:rate_limit_seconds"}),
        json.dumps({"path": path, "reason": "response:sent", "headers": {"Retry-After": "2"}}),
    ))
    assert _mode_observed(FaultMode.RATE_LIMIT_SECONDS, seconds, "", {path}, elapsed=1)
    assert not _mode_observed(
        FaultMode.RATE_LIMIT_SECONDS,
        seconds.replace('"2"', '"3"'),
        "",
        {path},
        elapsed=1,
    )
    http_date = seconds.replace("rate_limit_seconds", "rate_limit_http_date").replace(
        '"2"', '"Wed, 21 Oct 2015 07:28:00 GMT"'
    )
    assert _mode_observed(FaultMode.RATE_LIMIT_HTTP_DATE, http_date, "", {path}, elapsed=1)
    assert not _mode_observed(
        FaultMode.RATE_LIMIT_HTTP_DATE,
        http_date.replace("Wed, 21 Oct 2015 07:28:00 GMT", "in two seconds"),
        "",
        {path},
        elapsed=1,
    )


class _ClosingWriter:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.closed = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        if self.error:
            raise self.error


@pytest.mark.parametrize("error", [ConnectionResetError(), BrokenPipeError()])
async def test_close_writer_ignores_normal_peer_disconnects(error: OSError) -> None:
    """Closing an already-reset peer must not escape the server callback."""
    writer = _ClosingWriter(error)

    await _close_writer(writer)  # type: ignore[arg-type]

    assert writer.closed


async def test_close_writer_preserves_unrelated_close_errors() -> None:
    """Only expected peer disconnects are suppressed during server cleanup."""
    writer = _ClosingWriter(RuntimeError("unexpected close failure"))

    with pytest.raises(RuntimeError, match="unexpected close failure"):
        await _close_writer(writer)  # type: ignore[arg-type]


async def test_timeout_barrier_can_be_independently_released(tmp_path: Path) -> None:
    """A request records entry and only completes after its separate release signal."""
    corpus = load_manifest(_manifest(tmp_path), require_real=True)
    entered, release = tmp_path / "entered", tmp_path / "release"
    app = ReplayApplication(
        corpus, mode=FaultMode.TIMEOUT, barrier_entered=entered, barrier_release=release
    )
    task = asyncio.create_task(app.respond("GET", "/api/v1/organizations/org_001", ""))
    for _ in range(20):
        if entered.exists():
            break
        await asyncio.sleep(0.01)
    assert entered.exists()
    release.touch()
    assert await task == (None, {}, b"")
    assert [entry.reason for entry in app.journal][-2:] == ["barrier:entered", "barrier:released"]


async def test_faults_are_fail_closed_and_only_apply_to_selected_operation(tmp_path: Path) -> None:
    """A selected fault cannot intercept a different or unrecorded request."""
    organization = tmp_path / "organization.json"
    network = tmp_path / "network.json"
    organization.write_text('{"id":"org_001"}')
    network.write_text('[{"id":"network_001"}]')
    corpus = Corpus((
        Fixture(
            organization,
            "GET",
            "/api/v1/organizations/org_001",
            "",
            "getOrganization",
        ),
        Fixture(
            network,
            "GET",
            "/api/v1/organizations/org_001/networks",
            "",
            "getOrganizationNetworks",
        ),
    ))
    app = ReplayApplication(
        corpus,
        mode=FaultMode.UNAUTHORIZED,
        target_operation="getOrganizationNetworks",
    )
    assert await app.respond("GET", "/api/v1/organizations/org_001", "") == (
        200,
        {},
        b'{"id":"org_001"}',
    )
    assert await app.respond("GET", "/not-recorded", "") == (404, {}, b"")
    assert await app.respond("GET", "/api/v1/organizations/org_001/networks", "") == (401, {}, b"")


def test_tls_material_forms_a_valid_server_authentication_chain(tmp_path: Path) -> None:
    tls = create_tls_material(tmp_path)
    ca_certificate = x509.load_pem_x509_certificate(tls.ca_certificate.read_bytes())
    alternate_ca_certificate = x509.load_pem_x509_certificate(
        tls.alternate_ca_certificate.read_bytes()
    )
    server_certificate = x509.load_pem_x509_certificate(tls.server_certificate.read_bytes())

    server_certificate.verify_directly_issued_by(ca_certificate)
    assert ca_certificate.fingerprint(server_certificate.signature_hash_algorithm) != (
        alternate_ca_certificate.fingerprint(server_certificate.signature_hash_algorithm)
    )
    assert ca_certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    ca_key_usage = ca_certificate.extensions.get_extension_for_class(x509.KeyUsage).value
    assert ca_key_usage.key_cert_sign and ca_key_usage.crl_sign
    ca_subject_key_identifier = ca_certificate.extensions.get_extension_for_class(
        x509.SubjectKeyIdentifier
    ).value
    server_authority_key_identifier = server_certificate.extensions.get_extension_for_class(
        x509.AuthorityKeyIdentifier
    ).value
    assert server_authority_key_identifier.key_identifier == ca_subject_key_identifier.digest
    assert server_certificate.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
    assert not server_certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    server_key_usage = server_certificate.extensions.get_extension_for_class(x509.KeyUsage).value
    assert server_key_usage.digital_signature and server_key_usage.key_encipherment
    assert not server_key_usage.key_cert_sign and not server_key_usage.crl_sign
    server_extended_key_usage = server_certificate.extensions.get_extension_for_class(
        x509.ExtendedKeyUsage
    ).value
    assert ExtendedKeyUsageOID.SERVER_AUTH in server_extended_key_usage
    assert server_certificate.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value == (x509.SubjectAlternativeName([x509.DNSName("replay-origin")]))


def test_runner_resolves_exact_ids_and_always_tears_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command: list[str], **_: object) -> object:
        calls.append(tuple(command))
        if command[:3] == ["docker", "image", "inspect"]:
            return type("Result", (), {"stdout": "sha256:" + "a" * 64 + "\n"})()
        return type("Result", (), {"stdout": ""})()

    monkeypatch.setattr("tests.harness.runner.subprocess.run", fake_run)
    assert image_id("exporter:local") == "sha256:" + "a" * 64
    runner = HarnessRunner(
        _manifest(tmp_path), tmp_path / "artifacts", exporter_image="exporter:local"
    )
    monkeypatch.setattr(runner, "_probe_exporter", lambda *_: {"health": 200, "metrics": 200})
    monkeypatch.setattr(
        runner,
        "_wait_for_observation",
        lambda *_: ('{"path":"/api/v1/organizations/org_001","reason":"matched"}\n', "", 0.1),
    )
    runner.run([FaultMode.BASELINE])
    assert any(command[-2:] == ("down", "--volumes") for command in calls)


def test_runner_falls_back_to_bounded_exact_project_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timed-out Compose down removes only its labelled resources with bounded calls."""
    cleanup_calls: list[tuple[tuple[str, ...], object]] = []
    remaining = {"containers": ["container-for-project"], "networks": ["network-for-project"]}

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command[-2:] == ["down", "--volumes"]:
            cleanup_calls.append((tuple(command), kwargs.get("timeout")))
            raise subprocess.TimeoutExpired(command, cast(float, kwargs["timeout"]))
        if command[:3] == ["docker", "ps", "--all"]:
            cleanup_calls.append((tuple(command), kwargs.get("timeout")))
            value = "\n".join(remaining["containers"])
            remaining["containers"] = []
            return SimpleNamespace(stdout=value)
        if command[:3] == ["docker", "network", "ls"]:
            cleanup_calls.append((tuple(command), kwargs.get("timeout")))
            value = "\n".join(remaining["networks"])
            remaining["networks"] = []
            return SimpleNamespace(stdout=value)
        if command[:3] in (["docker", "rm", "--force"], ["docker", "network", "rm"]):
            cleanup_calls.append((tuple(command), kwargs.get("timeout")))
        return SimpleNamespace(stdout="")

    runner = HarnessRunner(
        _manifest(tmp_path), tmp_path / "artifacts", exporter_image="exporter:local"
    )
    monkeypatch.setattr("tests.harness.runner.image_id", lambda _: "sha256:" + "a" * 64)
    monkeypatch.setattr("tests.harness.runner.image_label", lambda *_: "sha256:" + "a" * 64)
    monkeypatch.setattr("tests.harness.runner._run", fake_run)
    monkeypatch.setattr(runner, "_probe_exporter", lambda *_: {"health": 200, "metrics": 200})
    monkeypatch.setattr(
        runner,
        "_wait_for_observation",
        lambda *_: ('{"path":"/api/v1/organizations/org_001","reason":"matched"}\n', "", 0.1),
    )

    runner.run([FaultMode.BASELINE])

    teardown_command = cleanup_calls[0][0]
    project = teardown_command[teardown_command.index("--project-name") + 1]
    exact_label = f"label=com.docker.compose.project={project}"
    assert all(timeout == 30 for _, timeout in cleanup_calls)
    assert all(
        exact_label in command
        for command, _ in cleanup_calls
        if command[:3] in (["docker", "ps", "--all"], ["docker", "network", "ls"])
    )
    assert ("docker", "rm", "--force", "container-for-project") in {
        command for command, _ in cleanup_calls
    }
    assert ("docker", "network", "rm", "network-for-project") in {
        command for command, _ in cleanup_calls
    }
    assert json.loads((tmp_path / "artifacts" / "evidence.json").read_text()) == [
        {
            "decision": "matched verified fixture",
            "journal_entries": 1,
            "mode": "baseline",
            "observation_seconds": 0.1,
            "observed": True,
            "probe": {"health": 200, "metrics": 200},
            "teardown_fallback": True,
        }
    ]
    assert json.loads((tmp_path / "artifacts" / "teardown-baseline.json").read_text()) == {
        "containers_removed": 1,
        "fallback_reason": "compose_timeout",
        "fallback_required": True,
        "networks_removed": 1,
        "outcome": "fallback_cleaned",
    }


@pytest.mark.parametrize(
    ("down_returncode", "leftovers", "fallback_reason"),
    [
        (1, False, "compose_nonzero"),
        (0, True, "resources_remaining"),
    ],
    ids=["nonzero-compose-down", "successful-compose-down-with-leftovers"],
)
def test_runner_falls_back_after_unsuccessful_or_incomplete_compose_down(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    down_returncode: int,
    leftovers: bool,
    fallback_reason: str,
) -> None:
    """Nonzero or incomplete Compose teardown gets the bounded exact-project fallback."""
    cleanup_calls: list[tuple[tuple[str, ...], object]] = []
    resources = {
        "containers": leftovers or down_returncode != 0,
        "networks": leftovers or down_returncode != 0,
    }

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command[-2:] == ["down", "--volumes"]:
            cleanup_calls.append((tuple(command), kwargs.get("timeout")))
            return SimpleNamespace(stdout="", returncode=down_returncode)
        if command[:3] == ["docker", "ps", "--all"]:
            cleanup_calls.append((tuple(command), kwargs.get("timeout")))
            return SimpleNamespace(
                stdout="container-for-project\n" if resources["containers"] else ""
            )
        if command[:3] == ["docker", "network", "ls"]:
            cleanup_calls.append((tuple(command), kwargs.get("timeout")))
            return SimpleNamespace(stdout="network-for-project\n" if resources["networks"] else "")
        if command[:3] == ["docker", "rm", "--force"]:
            cleanup_calls.append((tuple(command), kwargs.get("timeout")))
            resources["containers"] = False
        if command[:3] == ["docker", "network", "rm"]:
            cleanup_calls.append((tuple(command), kwargs.get("timeout")))
            resources["networks"] = False
        return SimpleNamespace(stdout="", returncode=0)

    runner = HarnessRunner(
        _manifest(tmp_path), tmp_path / "artifacts", exporter_image="exporter:local"
    )
    monkeypatch.setattr("tests.harness.runner.image_id", lambda _: "sha256:" + "a" * 64)
    monkeypatch.setattr("tests.harness.runner.image_label", lambda *_: "sha256:" + "a" * 64)
    monkeypatch.setattr("tests.harness.runner._run", fake_run)
    monkeypatch.setattr(runner, "_probe_exporter", lambda *_: {"health": 200, "metrics": 200})
    monkeypatch.setattr(
        runner,
        "_wait_for_observation",
        lambda *_: ('{"path":"/api/v1/organizations/org_001","reason":"matched"}\n', "", 0.1),
    )

    runner.run([FaultMode.BASELINE])

    teardown_command = cleanup_calls[0][0]
    project = teardown_command[teardown_command.index("--project-name") + 1]
    exact_label = f"label=com.docker.compose.project={project}"
    assert all(timeout == 30 for _, timeout in cleanup_calls)
    assert all(
        exact_label in command
        for command, _ in cleanup_calls
        if command[:3] in (["docker", "ps", "--all"], ["docker", "network", "ls"])
    )
    assert json.loads((tmp_path / "artifacts" / "teardown-baseline.json").read_text()) == {
        "containers_removed": 1,
        "fallback_reason": fallback_reason,
        "fallback_required": True,
        "networks_removed": 1,
        "outcome": "fallback_cleaned",
    }


def test_runner_records_clean_compose_teardown_after_exact_resource_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful down is only clean after its exact-project resources are absent."""
    calls: list[tuple[str, ...]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(tuple(command))
        return SimpleNamespace(stdout="", returncode=0)

    runner = HarnessRunner(
        _manifest(tmp_path), tmp_path / "artifacts", exporter_image="exporter:local"
    )
    monkeypatch.setattr("tests.harness.runner._run", fake_run)
    report: dict[str, object] = {"fallback_required": False}
    command = ["docker", "compose", "--project-name", "exact-project"]

    runner._teardown(command, {}, "exact-project", report)

    assert report == {"fallback_required": False, "outcome": "clean"}
    assert (
        "docker",
        "ps",
        "--all",
        "--quiet",
        "--filter",
        "label=com.docker.compose.project=exact-project",
    ) in calls
    assert (
        "docker",
        "network",
        "ls",
        "--quiet",
        "--filter",
        "label=com.docker.compose.project=exact-project",
    ) in calls


def test_runner_reports_unremoved_exact_project_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fallback that cannot prove removal fails after preserving its diagnostics."""

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command[-2:] == ["down", "--volumes"]:
            raise subprocess.TimeoutExpired(command, cast(float, kwargs["timeout"]))
        if command[:3] == ["docker", "ps", "--all"]:
            return SimpleNamespace(stdout="container-still-running\n")
        if command[:3] == ["docker", "network", "ls"]:
            return SimpleNamespace(stdout="")
        return SimpleNamespace(stdout="")

    runner = HarnessRunner(
        _manifest(tmp_path), tmp_path / "artifacts", exporter_image="exporter:local"
    )
    monkeypatch.setattr("tests.harness.runner.image_id", lambda _: "sha256:" + "a" * 64)
    monkeypatch.setattr("tests.harness.runner.image_label", lambda *_: "sha256:" + "a" * 64)
    monkeypatch.setattr("tests.harness.runner._run", fake_run)
    monkeypatch.setattr(runner, "_probe_exporter", lambda *_: {"health": 200, "metrics": 200})
    monkeypatch.setattr(
        runner,
        "_wait_for_observation",
        lambda *_: ('{"path":"/api/v1/organizations/org_001","reason":"matched"}\n', "", 0.1),
    )

    with pytest.raises(HarnessError, match="left exact-project resources"):
        runner.run([FaultMode.BASELINE])

    assert json.loads((tmp_path / "artifacts" / "evidence.json").read_text()) == [
        {
            "error": "exact-project cleanup left exact-project resources behind",
            "mode": "baseline",
            "observed": False,
            "teardown_fallback": True,
        }
    ]
    assert json.loads((tmp_path / "artifacts" / "teardown-baseline.json").read_text()) == {
        "containers_removed": 1,
        "fallback_reason": "compose_timeout",
        "fallback_required": True,
        "networks_removed": 0,
        "outcome": "fallback_failed",
        "remaining_containers": 1,
        "remaining_networks": 0,
    }


def test_runner_retains_partial_aggregate_evidence_when_a_later_mode_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = HarnessRunner(
        _manifest(tmp_path), tmp_path / "artifacts", exporter_image="exporter:local"
    )
    monkeypatch.setattr("tests.harness.runner.image_id", lambda _: "sha256:" + "a" * 64)
    monkeypatch.setattr("tests.harness.runner.image_label", lambda *_: "sha256:" + "a" * 64)
    monkeypatch.setattr("tests.harness.runner._run", lambda *_args, **_kwargs: None)
    results = iter(({"mode": "baseline", "observed": True}, HarnessError("later mode failed")))

    def run_mode(*_args: object) -> dict[str, object]:
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(runner, "_run_mode", run_mode)
    with pytest.raises(HarnessError, match="later mode failed"):
        runner.run([FaultMode.BASELINE, FaultMode.RESET])
    evidence = json.loads((tmp_path / "artifacts" / "evidence.json").read_text())
    assert evidence == [
        {"mode": "baseline", "observed": True},
        {
            "error": "later mode failed",
            "mode": "reset",
            "observed": False,
            "teardown_fallback": False,
        },
    ]


def test_runner_retains_redacted_failed_mode_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mode failure leaves journal/log evidence and unconditional Compose teardown behind."""
    calls: list[tuple[str, ...]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(tuple(command))
        if command[:3] in (["docker", "ps", "--all"], ["docker", "network", "ls"]):
            return SimpleNamespace(stdout="", returncode=0)
        return SimpleNamespace(stdout="harness-sentinel-not-a-secret")

    runner = HarnessRunner(
        _manifest(tmp_path), tmp_path / "artifacts", exporter_image="exporter:local"
    )
    monkeypatch.setattr("tests.harness.runner.image_id", lambda _: "sha256:" + "a" * 64)
    monkeypatch.setattr("tests.harness.runner.image_label", lambda *_: "sha256:" + "a" * 64)
    monkeypatch.setattr("tests.harness.runner._run", fake_run)
    monkeypatch.setattr(
        runner,
        "_probe_exporter",
        lambda *_: (_ for _ in ()).throw(HarnessError("probe failed")),
    )

    with pytest.raises(HarnessError, match="probe failed"):
        runner.run([FaultMode.BASELINE])

    artifacts = tmp_path / "artifacts"
    assert "[REDACTED]" in (artifacts / "compose-baseline.log").read_text()
    assert (artifacts / "journal-baseline.jsonl").exists()
    assert json.loads((artifacts / "evidence.json").read_text()) == [
        {
            "error": "probe failed",
            "mode": "baseline",
            "observed": False,
            "teardown_fallback": False,
        }
    ]
    assert any(command[-2:] == ("down", "--volumes") for command in calls)


def test_compose_has_exact_env_keys_and_immutable_images() -> None:
    compose = Path("tests/harness/compose.yml").read_text(encoding="utf-8")
    for key in (
        "MERAKI_EXPORTER_MERAKI__API_KEY",
        "MERAKI_EXPORTER_MERAKI__ORG_ID",
        "MERAKI_EXPORTER_MERAKI__API_BASE_URL",
        "MERAKI_EXPORTER_MERAKI__ALLOW_CUSTOM_API_BASE_URL",
        "MERAKI_EXPORTER_COLLECTORS__PROFILE=availability",
        "MERAKI_EXPORTER_COLLECTORS__ENABLED_COLLECTORS=device",
        "MERAKI_EXPORTER_API__TIMEOUT",
        "MERAKI_EXPORTER_API__MAX_RETRIES",
        "MERAKI_EXPORTER_SERVER__PORT=9099",
    ):
        assert key in compose
    assert "MERAKI_EXPORTER_MERAKI__ORG_ID=org_001" in compose
    assert "MERAKI_EXPORTER_API__MAX_RETRIES=1" in compose
    assert compose.count("pull_policy: never") == 2
    assert compose.count('com.centurylinklabs.watchtower.enable: "false"') == 2
    assert "internal: true" in compose and "${HARNESS_IMAGE_ID:?" in compose
    dockerignore = Path("tests/harness/Dockerfile.dockerignore").read_text(encoding="utf-8")
    assert "!tests/harness/**" in dockerignore
    dockerfile = Path("tests/harness/Dockerfile").read_text(encoding="utf-8")
    assert "FROM ${EXPORTER_IMAGE}" in dockerfile
    assert "io.m7kni.failure-harness.base-image-id=${EXPORTER_IMAGE_ID}" in dockerfile


def test_wiring_mentions_only_manual_dispatch_and_local_commands() -> None:
    workflow = Path(".github/workflows/failure-harness.yml").read_text(encoding="utf-8")
    assert (
        "workflow_dispatch:" in workflow
        and "push:" not in workflow
        and "pull_request:" not in workflow
    )
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "harness-validate" in Path("justfile").read_text(encoding="utf-8")
    assert "Failure Harness" in Path("docs.toml").read_text(encoding="utf-8")
