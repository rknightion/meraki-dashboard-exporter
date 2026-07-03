"""Tests for OrganizationCollector Phase 4 coordinator methods (#297, #298)."""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry
from pydantic import SecretStr

from meraki_dashboard_exporter.collectors.organization import OrganizationCollector
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.services.inventory import OrganizationInventory
from tests.helpers.factories import NetworkFactory
from tests.helpers.mock_api import MockAPIBuilder

ORG_ID = "org1"
ORG_NAME = "Org One"


def _settings() -> Settings:
    return Settings(
        meraki=MerakiSettings(api_key=SecretStr("a" * 40), org_id=ORG_ID),
    )


def _build(builder: MockAPIBuilder) -> tuple[OrganizationCollector, CollectorRegistry]:
    settings = _settings()
    api = builder.build()
    inventory = OrganizationInventory(api, settings)
    registry = CollectorRegistry()
    collector = OrganizationCollector(
        api=api,
        settings=settings,
        registry=registry,
        inventory=inventory,
    )
    return collector, registry


class TestConfigTemplates:
    """#297 — config templates + template binding."""

    async def test_template_count_and_bound_networks(self):
        """Template count + count of filtered networks bound to a template."""
        builder = (
            MockAPIBuilder()
            .with_custom_response("getOrganizationConfigTemplates", [{"id": "t1"}, {"id": "t2"}])
            .with_networks(
                [
                    NetworkFactory.create(
                        network_id="N1", org_id=ORG_ID, isBoundToConfigTemplate=True
                    ),
                    NetworkFactory.create(
                        network_id="N2", org_id=ORG_ID, isBoundToConfigTemplate=False
                    ),
                    NetworkFactory.create(
                        network_id="N3", org_id=ORG_ID, isBoundToConfigTemplate=True
                    ),
                ],
                org_id=ORG_ID,
            )
        )
        collector, registry = _build(builder)

        await collector._collect_config_templates(ORG_ID, ORG_NAME)

        assert registry.get_sample_value("meraki_org_config_templates", {"org_id": ORG_ID}) == 2
        assert (
            registry.get_sample_value("meraki_org_networks_bound_to_template", {"org_id": ORG_ID})
            == 2
        )

    async def test_no_templates_is_zero(self):
        """An org with no templates reports 0 for both gauges."""
        builder = (
            MockAPIBuilder()
            .with_custom_response("getOrganizationConfigTemplates", [])
            .with_networks([NetworkFactory.create(network_id="N1", org_id=ORG_ID)], org_id=ORG_ID)
        )
        collector, registry = _build(builder)

        await collector._collect_config_templates(ORG_ID, ORG_NAME)

        assert registry.get_sample_value("meraki_org_config_templates", {"org_id": ORG_ID}) == 0
        assert (
            registry.get_sample_value("meraki_org_networks_bound_to_template", {"org_id": ORG_ID})
            == 0
        )


class TestAdaptivePolicy:
    """#298 — adaptive policy overview."""

    async def test_counts_emitted(self):
        """Adaptive policy groups/acls/policies counts are emitted."""
        builder = MockAPIBuilder().with_custom_response(
            "getOrganizationAdaptivePolicyOverview",
            {"counts": {"groups": 3, "customAcls": 2, "policies": 5}},
        )
        collector, registry = _build(builder)

        await collector._collect_adaptive_policy(ORG_ID, ORG_NAME)

        assert (
            registry.get_sample_value("meraki_org_adaptive_policy_groups", {"org_id": ORG_ID}) == 3
        )
        assert registry.get_sample_value("meraki_org_adaptive_policy_acls", {"org_id": ORG_ID}) == 2
        assert (
            registry.get_sample_value("meraki_org_adaptive_policy_policies", {"org_id": ORG_ID})
            == 5
        )

    async def test_404_is_soft_skip(self):
        """Unlicensed org 404s: no metrics set, no exception raised."""
        builder = MockAPIBuilder().with_error(
            "getOrganizationAdaptivePolicyOverview", Exception("404 Not Found")
        )
        collector, registry = _build(builder)

        await collector._collect_adaptive_policy(ORG_ID, ORG_NAME)

        assert (
            registry.get_sample_value("meraki_org_adaptive_policy_groups", {"org_id": ORG_ID})
            is None
        )

    async def test_real_error_raises(self):
        """A non-404/400 error propagates so the coordinator counts a failure."""
        builder = MockAPIBuilder().with_error(
            "getOrganizationAdaptivePolicyOverview", Exception("Connection error")
        )
        collector, _ = _build(builder)

        with pytest.raises(Exception, match="Connection error"):
            await collector._collect_adaptive_policy(ORG_ID, ORG_NAME)
