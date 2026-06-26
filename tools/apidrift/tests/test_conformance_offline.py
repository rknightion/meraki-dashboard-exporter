"""Guard the offline conformance entrypoint against the vendored spec."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_offline_conformance_runs_against_vendored_spec() -> None:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(["src", "tools"])}
    spec = "spec/meraki-openapi.json.gz"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "apidrift",
            "--baseline",
            spec,
            "--live",
            spec,
            "--src",
            "src",
            "--conformance-only",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    # Must not crash. Exit 0 (clean) or 3 (pre-existing model drift to triage).
    assert result.returncode in (0, 3), result.stderr
