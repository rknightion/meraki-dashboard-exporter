"""Tests for ConfigCollector SAML/SSO posture (#301)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry
from pydantic import SecretStr

from meraki_dashboard_exporter.collectors.config import ConfigCollector
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.services.inventory import OrganizationInventory
from tests.helpers.mock_api import MockAPIBuilder

ORG_ID = "org1"
ORG_NAME = "Org One"


def _settings() -> Settings:
    return Settings(
        meraki=MerakiSettings(api_key=SecretStr("a" * 40), org_id=ORG_ID),
    )


def _build(builder: MockAPIBuilder) -> tuple[ConfigCollector, CollectorRegistry]:
    settings = _settings()
    api = builder.build()
    inventory = OrganizationInventory(api, settings)
    registry = CollectorRegistry()
    collector = ConfigCollector(
        api=api,
        settings=settings,
        registry=registry,
        inventory=inventory,
    )
    return collector, registry


class TestConfigSaml:
    """#301 — SAML/SSO posture."""

    async def test_saml_enabled_with_idps(self):
        """SAML enabled -> enabled=1 and configured IdP count emitted."""
        builder = (
            MockAPIBuilder()
            .with_custom_response("getOrganizationSaml", {"enabled": True})
            .with_custom_response("getOrganizationSamlIdps", [{"idpId": "a"}, {"idpId": "b"}])
        )
        collector, registry = _build(builder)

        await collector._collect_saml(ORG_ID, ORG_NAME)

        assert registry.get_sample_value("meraki_org_saml_enabled", {"org_id": ORG_ID}) == 1
        assert registry.get_sample_value("meraki_org_saml_idps", {"org_id": ORG_ID}) == 2

    async def test_saml_disabled_skips_idp_call(self):
        """SAML disabled -> enabled=0, idps=0, and the IdP endpoint is not called."""
        builder = (
            MockAPIBuilder()
            .with_custom_response("getOrganizationSaml", {"enabled": False})
            .with_custom_response("getOrganizationSamlIdps", [{"idpId": "a"}])
        )
        collector, registry = _build(builder)

        await collector._collect_saml(ORG_ID, ORG_NAME)

        assert registry.get_sample_value("meraki_org_saml_enabled", {"org_id": ORG_ID}) == 0
        assert registry.get_sample_value("meraki_org_saml_idps", {"org_id": ORG_ID}) == 0
        # IdP endpoint must not be queried when SAML is disabled.
        assert not collector.api.organizations.getOrganizationSamlIdps.called

    async def test_saml_settings_404_emits_zeros(self):
        """SAML settings endpoint 404 -> both gauges emit explicit zeros."""
        builder = MockAPIBuilder().with_error("getOrganizationSaml", Exception("404 Not Found"))
        collector, registry = _build(builder)

        await collector._collect_saml(ORG_ID, ORG_NAME)

        assert registry.get_sample_value("meraki_org_saml_enabled", {"org_id": ORG_ID}) == 0
        assert registry.get_sample_value("meraki_org_saml_idps", {"org_id": ORG_ID}) == 0

    async def test_saml_idps_400_when_enabled_is_tolerated(self):
        """SAML enabled but IdP endpoint 400s -> enabled=1, idps=0, no raise."""
        builder = (
            MockAPIBuilder()
            .with_custom_response("getOrganizationSaml", {"enabled": True})
            .with_error("getOrganizationSamlIdps", Exception("400 Bad Request"))
        )
        collector, registry = _build(builder)

        await collector._collect_saml(ORG_ID, ORG_NAME)

        assert registry.get_sample_value("meraki_org_saml_enabled", {"org_id": ORG_ID}) == 1
        assert registry.get_sample_value("meraki_org_saml_idps", {"org_id": ORG_ID}) == 0
