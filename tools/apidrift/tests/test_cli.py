"""End-to-end CLI tests (subprocess so PYTHONPATH wiring is exercised)."""

from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV = {**os.environ, "PYTHONPATH": "tools"}


def _write_spec(path: Path, ops: list[str]) -> None:
    paths = {
        f"/{op}": {
            "get": {
                "operationId": op,
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"type": "object"}}}}
                },
            }
        }
        for op in ops
    }
    spec = {"openapi": "3.0.1", "info": {"title": "t", "version": "1"}, "paths": paths}
    path.write_bytes(gzip.compress(json.dumps(spec).encode()))


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "apidrift", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=ENV,
    )


def test_cli_exit_3_when_consumed_op_removed(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.py").write_text("self.api.organizations.getOrganizations()\n")
    base = tmp_path / "base.json.gz"
    live = tmp_path / "live.json.gz"
    _write_spec(base, ["getOrganizations"])  # baseline has the op
    _write_spec(live, [])  # live removed it upstream
    r = _run([
        "--baseline",
        str(base),
        "--live",
        str(live),
        "--src",
        str(src),
        "--format",
        "md",
        "--no-conformance",
    ])
    assert r.returncode == 3, r.stderr
    assert "getOrganizations" in r.stdout


def test_cli_exit_0_when_clean(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.py").write_text("self.api.organizations.getOrganizations()\n")
    base = tmp_path / "base.json.gz"
    live = tmp_path / "live.json.gz"
    _write_spec(base, ["getOrganizations"])
    _write_spec(live, ["getOrganizations"])
    r = _run([
        "--baseline",
        str(base),
        "--live",
        str(live),
        "--src",
        str(src),
        "--no-conformance",
    ])
    assert r.returncode == 0, r.stderr
    assert "No drift" in r.stdout


def test_cli_emit_reduced_writes_specs(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.py").write_text("self.api.organizations.getOrganizations()\n")
    base = tmp_path / "base.json.gz"
    live = tmp_path / "live.json.gz"
    _write_spec(base, ["getOrganizations"])
    _write_spec(live, ["getOrganizations"])
    out = tmp_path / "reduced"
    r = _run([
        "--baseline",
        str(base),
        "--live",
        str(live),
        "--src",
        str(src),
        "--no-conformance",
        "--emit-reduced",
        str(out),
    ])
    assert r.returncode == 0, r.stderr
    reduced = json.loads((out / "live.json").read_text())
    assert "/getOrganizations" in reduced["paths"]


def test_cli_load_error_exit_2(tmp_path: Path) -> None:
    r = _run(["--baseline", str(tmp_path / "nope.json"), "--live", str(tmp_path / "x.json")])
    assert r.returncode == 2, r.stderr


def test_cli_coverage_runs_standalone_without_spec() -> None:
    # --coverage needs no --baseline/--live and must import the real models, so it
    # needs src on the path alongside tools.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(["src", "tools"])}
    r = subprocess.run(
        [sys.executable, "-m", "apidrift", "--coverage", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    cov = json.loads(r.stdout)
    # Every registered model is classified; the sum of buckets equals the total.
    assert cov["total"] == len(cov["mapped"]) + len(cov["derived"]) + len(cov["unmapped"])
    assert cov["total"] > 0
