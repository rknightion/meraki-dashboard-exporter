"""Guard the offline conformance entrypoint against the vendored spec."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import structlog

import meraki_dashboard_exporter
from apidrift.conformance import coverage
from apidrift.models import conformance_models

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_response_model_discovery_and_coverage() -> None:
    models = conformance_models()
    names = {model.__name__ for model in models}
    assert {"ApiRequestEntry", "MGUplinkStatusRow"} <= names
    assert not {"CollectorTriggerRequest", "Settings", "APISettings"} & names
    assert coverage(models).unmapped == []


@pytest.mark.parametrize("configured", [False, True])
def test_discovery_propagates_package_import_errors_and_restores_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: bool
) -> None:
    package = tmp_path / "broken_discovery_package"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from pathlib import Path\n"
        "marker = Path(__file__).with_name('attempted')\n"
        "if not marker.exists():\n"
        "    marker.touch()\n"
        '    raise ImportError("synthetic package failure")\n'
    )
    monkeypatch.setattr(meraki_dashboard_exporter, "__path__", [str(tmp_path)])
    original_config, original_configured = structlog.get_config(), structlog.is_configured()
    try:
        structlog.reset_defaults()
        if configured:
            structlog.configure(cache_logger_on_first_use=True)
        expected = structlog.get_config()
        with pytest.raises(ImportError, match="synthetic package failure"):
            conformance_models()
        assert structlog.get_config() == expected
        assert structlog.is_configured() is configured
    finally:
        structlog.reset_defaults()
        if original_configured:
            structlog.configure(**original_config)


def test_discovery_does_not_cache_temporary_logger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "logging_discovery_package"
    package.mkdir()
    (package / "__init__.py").write_text(
        'import structlog\nlogger = structlog.get_logger()\nlogger.info("during")\n'
    )
    monkeypatch.setattr(meraki_dashboard_exporter, "__path__", [str(tmp_path)])
    original_config, original_configured = structlog.get_config(), structlog.is_configured()
    output = io.StringIO()
    try:
        structlog.configure(
            processors=[structlog.processors.KeyValueRenderer()],
            logger_factory=structlog.PrintLoggerFactory(file=output),
            cache_logger_on_first_use=True,
        )
        conformance_models()
        module = sys.modules["meraki_dashboard_exporter.logging_discovery_package"]
        module.logger.info("after")
        assert "after" in output.getvalue()
    finally:
        sys.modules.pop("meraki_dashboard_exporter.logging_discovery_package", None)
        structlog.reset_defaults()
        if original_configured:
            structlog.configure(**original_config)


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
    json.loads(result.stdout)
