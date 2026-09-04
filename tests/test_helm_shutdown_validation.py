"""Render and generator contracts for Helm shutdown-grace validation (MDE-0023)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
CHART = REPO_ROOT / "charts" / "meraki-dashboard-exporter"
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_helm_config.py"
SHUTDOWN_DEADLINE_ENV = "MERAKI_EXPORTER_API__PER_FETCH_DEADLINE_SECONDS"
SERVER_PORT_ENV = "MERAKI_EXPORTER_SERVER__PORT"


def _load_generator() -> ModuleType:
    """Load the Helm generator without treating ``scripts`` as a package."""
    module_name = "mde_0023_generate_helm_config"
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _helm_template(*args: str) -> subprocess.CompletedProcess[str]:
    """Render the chart with an API key and any additional Helm arguments."""
    command = [
        "helm",
        "template",
        "test-release",
        str(CHART),
        "--set",
        "meraki.apiKey=dummy",
        *args,
    ]
    return subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)


def test_generator_shutdown_default_matches_schema_knob() -> None:
    """The generated fallback is taken from the Settings-derived knob default."""
    generator = _load_generator()
    knobs = generator.collect_knobs()
    schema_default = next(k["default"] for k in knobs if k["env"] == SHUTDOWN_DEADLINE_ENV)

    block = generator.render_shutdown_validation_block(knobs)

    assert generator.VALIDATION_BEGIN in block
    assert f"default {schema_default} .Values.config.apiPerFetchDeadlineSeconds" in block
    assert generator.VALIDATION_END in block
    assert block in (CHART / "templates" / "_validation.tpl").read_text()


def test_generator_tracks_a_changed_schema_default() -> None:
    """A changed schema knob default changes the generated Helm assignment."""
    generator = _load_generator()
    knobs = [dict(knob) for knob in generator.collect_knobs()]
    target = next(k for k in knobs if k["env"] == SHUTDOWN_DEADLINE_ENV)
    target["default"] = "321"

    block = generator.render_shutdown_validation_block(knobs)

    assert "default 321 .Values.config.apiPerFetchDeadlineSeconds" in block


def test_helm_render_accepts_schema_default() -> None:
    """The chart renders with its default grace period and generated fallback."""
    result = _helm_template()

    assert result.returncode == 0, result.stderr
    assert "terminationGracePeriodSeconds: 150" in result.stdout


def test_helm_render_accepts_valid_deadline_override() -> None:
    """The shutdown margin is preserved for an explicitly configured deadline."""
    result = _helm_template(
        "--set",
        "config.apiPerFetchDeadlineSeconds=180",
        "--set",
        "terminationGracePeriodSeconds=210",
    )

    assert result.returncode == 0, result.stderr
    assert "terminationGracePeriodSeconds: 210" in result.stdout
    assert 'MERAKI_EXPORTER_API__PER_FETCH_DEADLINE_SECONDS: "180"' in result.stdout


def test_helm_render_rejects_insufficient_grace_for_deadline() -> None:
    """A grace period below deadline plus the 30-second margin fails at render time."""
    result = _helm_template(
        "--set",
        "config.apiPerFetchDeadlineSeconds=180",
        "--set",
        "terminationGracePeriodSeconds=209",
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "must be at least config.apiPerFetchDeadlineSeconds + 30 (210); got 209" in output


def test_helm_render_rejects_deadline_extra_env_bypass() -> None:
    """The deadline cannot bypass render-time validation through ``extraEnv``."""
    result = _helm_template(
        "--set",
        f"extraEnv[0].name={SHUTDOWN_DEADLINE_ENV}",
        "--set",
        "extraEnv[0].value=999",
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "extraEnv may not set MERAKI_EXPORTER_API__PER_FETCH_DEADLINE_SECONDS" in output


def test_helm_render_rejects_mixed_case_deadline_extra_env_bypass() -> None:
    """Pydantic's case-insensitive settings cannot bypass deadline validation."""
    result = _helm_template(
        "--set",
        "extraEnv[0].name=meraki_exporter_api__per_fetch_deadline_seconds",
        "--set",
        "extraEnv[0].value=999",
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "extraEnv may not set MERAKI_EXPORTER_API__PER_FETCH_DEADLINE_SECONDS" in output


def test_helm_render_rejects_server_port_extra_env_bypass() -> None:
    """The listener port cannot diverge from the chart's service port."""
    result = _helm_template(
        "--set",
        f"extraEnv[0].name={SERVER_PORT_ENV}",
        "--set",
        "extraEnv[0].value=8080",
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "extraEnv may not set MERAKI_EXPORTER_SERVER__PORT; use service.port" in output


def test_helm_render_rejects_mixed_case_server_port_extra_env_bypass() -> None:
    """Pydantic's case-insensitive settings cannot bypass listener validation."""
    result = _helm_template(
        "--set",
        "extraEnv[0].name=Meraki_Exporter_Server__Port",
        "--set",
        "extraEnv[0].value=8080",
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "extraEnv may not set MERAKI_EXPORTER_SERVER__PORT; use service.port" in output


def test_helm_render_preserves_ordinary_extra_env() -> None:
    """Unrelated environment variables preserve the chart-owned port wiring."""
    result = _helm_template(
        "--set",
        "service.port=9191",
        "--set",
        "extraEnv[0].name=EXAMPLE_UNRELATED_SETTING",
        "--set",
        "extraEnv[0].value=accepted",
    )

    assert result.returncode == 0, result.stderr
    assert "name: EXAMPLE_UNRELATED_SETTING" in result.stdout
    assert "value: accepted" in result.stdout
    assert 'MERAKI_EXPORTER_SERVER__PORT: "9191"' in result.stdout
    assert "containerPort: 9191" in result.stdout
    assert "- port: 9191\n      targetPort: http" in result.stdout
    assert result.stdout.count("port: http") == 2
