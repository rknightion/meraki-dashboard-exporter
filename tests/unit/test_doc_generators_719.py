"""Regression coverage for documentation generator failure handling (#719)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import generate_collector_docs as gcd_collectors  # noqa: E402
import generate_config_docs as gcd_config  # noqa: E402
import generate_endpoints_docs as ged  # noqa: E402
import generate_env_example as gee  # noqa: E402
import generate_metrics_docs as gcd_metrics  # noqa: E402
import generate_scaling_capacity_docs as gscd  # noqa: E402
import validate_documented_env_vars as vdev  # noqa: E402


def test_metrics_scan_fails_on_unparseable_source(tmp_path: Path) -> None:
    """A syntax error must abort generation instead of silently omitting metrics."""
    broken_source = tmp_path / "broken.py"
    broken_source.write_text("def broken(:\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Error parsing"):
        gcd_metrics.scan_for_metrics(tmp_path, tmp_path, {}, {})


def test_collector_scan_fails_on_unparseable_source(tmp_path: Path) -> None:
    """A syntax error must abort generation instead of silently omitting collectors."""
    collectors_dir = tmp_path / "meraki_dashboard_exporter" / "collectors"
    collectors_dir.mkdir(parents=True)
    (collectors_dir / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Error parsing"):
        gcd_collectors.scan_for_collectors(tmp_path, tmp_path)


def test_metrics_require_at_least_one_definition() -> None:
    """An empty metric scan is a broken generator, not valid documentation."""
    with pytest.raises(RuntimeError, match="No metric definitions"):
        gcd_metrics.require_metric_definitions([])


def test_collectors_require_at_least_one_definition() -> None:
    """An empty collector scan is a broken generator, not valid documentation."""
    with pytest.raises(RuntimeError, match="No collector definitions"):
        gcd_collectors.require_collector_definitions([])


def test_config_sections_must_match_settings_tree() -> None:
    """config.md's explicit sections cannot omit a Settings subtree."""
    repo_root = gcd_config.find_repo_root(SCRIPTS_DIR)
    settings = gee.load_settings_model(repo_root)
    config_models = gcd_config.load_config_models(repo_root)
    nested_models = gcd_config.get_nested_models(config_models)

    with pytest.raises(RuntimeError, match="does not match Settings"):
        gcd_config.validate_nested_models(nested_models[:-1], settings)


def test_720_endpoint_notes_reject_a_nontrivial_route_without_a_contract_note() -> None:
    """Generated endpoint docs cannot silently ship a blank auth/side-effect note (#720)."""
    endpoint = ged.Endpoint("POST", "/unreviewed", "Does work", "app.py", 1)
    with pytest.raises(RuntimeError, match="/unreviewed"):
        ged.validate_endpoint_notes([endpoint])


def test_endpoint_docs_preserve_front_matter_and_one_terminal_newline() -> None:
    """The generated Zensical page keeps its metadata and is byte-stable."""
    endpoint = ged.Endpoint("GET", "/health", "Health check", "app.py", 1)

    rendered = ged.generate_markdown([endpoint])

    assert rendered.startswith(
        "---\ntitle: HTTP Endpoints\ndescription: Reference the Meraki Dashboard Exporter"
    )
    assert rendered.endswith("disabled.\n")
    assert not rendered.endswith("\n\n")


def test_720_scaling_region_is_source_derived_and_distinguishes_due_sweep() -> None:
    """The capacity region is derived from endpoint groups, not hand-maintained (#720)."""
    rendered = gscd.render_network_health_capacity(SCRIPTS_DIR.parents[0] / "src")
    assert "**4.58**" in rendered
    assert "**1,041.3**" in rendered
    assert "due sweep" in rendered


def test_720_scaling_region_requires_markers(tmp_path: Path) -> None:
    """A scaling guide without the owned marker range is rejected (#720)."""
    guide = tmp_path / "scaling-guide.md"
    guide.write_text("# Scaling\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="markers"):
        gscd.replace_generated_region(guide, "generated")


def test_720_documented_env_validation_rejects_wrong_webhook_secret(tmp_path: Path) -> None:
    """Customer-facing examples must use the real webhook secret setting (#720)."""
    example = tmp_path / "example.md"
    example.write_text("MERAKI_EXPORTER_WEBHOOKS__SECRET=value\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="WEBHOOKS__SECRET"):
        vdev.validate_documented_env_vars([example], {"MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET"})


def test_720_documented_env_validation_accepts_real_webhook_secret(tmp_path: Path) -> None:
    """The real webhook shared-secret variable remains accepted (#720)."""
    example = tmp_path / "example.md"
    example.write_text("MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET=value\n", encoding="utf-8")
    vdev.validate_documented_env_vars([example], {"MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET"})
