"""Full-runtime, corpus-backed resource measurement for the D11 calibration.

This module intentionally measures only HOMELAB.  The retained corpus contains
only that topology's live-verified organization/device routes, so scaling it by
duplicating rows or substituting a generated FleetFixture would manufacture API
responses and invalidate the result.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from tests.fixtures.fleet import FleetPreset
from tests.harness.corpus import load_manifest
from tests.harness.runner import COMPOSE_FILE, HarnessRunner, _run
from tests.harness.server import FaultMode, fault_decision
from tests.harness.tls import create_tls_material

DEFAULT_MANIFEST: Final = Path("tests/harness/corpus/manifest.json")
DEFAULT_EXPORTER_IMAGE: Final = "meraki-dashboard-exporter:failure-harness"


@dataclass(frozen=True)
class FullRuntimeMeasurement:
    """One actual HTTP scrape from the disposable full ExporterApp runtime."""

    preset: FleetPreset
    http_status: int
    rss_bytes: int
    sample_lines: int
    product_sample_lines: int
    payload_bytes: int
    scrape_render_seconds: float
    corpus_operations: tuple[str, ...]


def measure_homelab(
    *,
    manifest: Path = DEFAULT_MANIFEST,
    exporter_image: str = DEFAULT_EXPORTER_IMAGE,
) -> FullRuntimeMeasurement:
    """Run the live-verified HOMELAB corpus through the full exporter process."""
    corpus = load_manifest(manifest, require_real=True)
    with tempfile.TemporaryDirectory(prefix="fleet-measurement-") as temporary:
        runtime = Path(temporary)
        shutil.copytree(manifest.parent, runtime / "corpus")
        create_tls_material(runtime)
        (runtime / "journal.jsonl").touch(mode=0o666)

        runner = HarnessRunner(manifest, runtime, exporter_image=exporter_image)
        exporter_id, proxy_id = runner._build_images()
        project = f"fleet-measurement-{int(time.time() * 1000)}"
        decision = fault_decision(FaultMode.BASELINE)
        environment = {
            "HARNESS_IMAGE_ID": exporter_id,
            "HARNESS_PROXY_IMAGE_ID": proxy_id,
            "HARNESS_RUNTIME_DIR": str(runtime),
            "HARNESS_MODE": FaultMode.BASELINE.value,
            "HARNESS_TARGET_OPERATION": "",
            "HARNESS_ORIGIN_HOST": decision.origin_host,
            "HARNESS_TRUSTED_CA": "trusted-ca.pem",
            "HARNESS_PROFILE": "full",
            "HARNESS_ENABLED_COLLECTORS": (
                "alerts,clients,config,device,mtsensor,mtsensoralerts,"
                "networkhealth,organization,insight"
            ),
            "HARNESS_CLIENTS_ENABLED": "true",
            "HARNESS_EXECUTOR_WORKERS": "25",
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
        try:
            _run([*command, "up", "--detach", "--no-build"], env=environment)
            runner._probe_exporter(command, environment)
            runner._wait_for_observation(
                command,
                environment,
                runtime,
                FaultMode.BASELINE,
                {
                    (fixture.method, fixture.path, fixture.query): fixture.status_code
                    for fixture in corpus.fixtures
                    if fixture.sdk_operation != "getOrganizations"
                },
                timeout_seconds=180,
            )
            result = _run(
                [
                    *command,
                    "exec",
                    "--no-TTY",
                    "exporter",
                    "python",
                    "-c",
                    _TIMED_SCRAPE_SCRIPT,
                ],
                env=environment,
            )
        finally:
            runner._teardown(command, environment, project, teardown)

    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError("timed scraper did not return a JSON object")
    return FullRuntimeMeasurement(
        preset=FleetPreset.HOMELAB,
        http_status=int(data["http_status"]),
        rss_bytes=int(data["rss_bytes"]),
        sample_lines=int(data["sample_lines"]),
        product_sample_lines=int(data["product_sample_lines"]),
        payload_bytes=int(data["payload_bytes"]),
        scrape_render_seconds=float(data["scrape_render_seconds"]),
        corpus_operations=tuple(sorted(fixture.sdk_operation for fixture in corpus.fixtures)),
    )


_TIMED_SCRAPE_SCRIPT: Final = """
import json
import time

import httpx
import psutil

started = time.perf_counter()
response = httpx.get("http://127.0.0.1:9099/metrics", timeout=30)
elapsed = time.perf_counter() - started
lines = [line for line in response.text.splitlines() if line and not line.startswith("#")]
product = [line for line in lines if line.startswith("meraki_") and not line.startswith("meraki_exporter_")]
print(json.dumps({
    "http_status": response.status_code,
    "rss_bytes": psutil.Process(1).memory_info().rss,
    "sample_lines": len(lines),
    "product_sample_lines": len(product),
    "payload_bytes": len(response.content),
    "scrape_render_seconds": elapsed,
}))
"""


def main() -> None:
    """Print a portable, no-body measurement record for the calibrated corpus."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--exporter-image", default=DEFAULT_EXPORTER_IMAGE)
    arguments = parser.parse_args()
    print(
        json.dumps(
            asdict(
                measure_homelab(
                    manifest=arguments.manifest, exporter_image=arguments.exporter_image
                )
            )
        )
    )


if __name__ == "__main__":
    main()
