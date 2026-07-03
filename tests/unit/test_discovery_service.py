"""Tests for the DiscoveryService using test helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.discovery import (
    DiscoveryService,
    OrgResolutionError,
    resolve_org_id,
)
from tests.helpers.factories import NetworkFactory, OrganizationFactory


@pytest.fixture
def mock_settings(monkeypatch):
    """Create mock settings."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    settings = Settings()
    return settings


@pytest.fixture
def discovery_service(mock_api, mock_settings):
    """Create a DiscoveryService instance."""
    return DiscoveryService(api=mock_api, settings=mock_settings)


@pytest.fixture
def mock_api():
    """Create a mock Meraki API client."""
    mock = MagicMock()
    mock.organizations = MagicMock()
    return mock


class TestDiscoveryService:
    """Test DiscoveryService functionality."""

    @pytest.mark.asyncio
    async def test_run_discovery_with_single_org(self, mock_api, mock_settings):
        """Test discovery with a specific org_id configured."""
        mock_settings.meraki.org_id = "123"
        service = DiscoveryService(api=mock_api, settings=mock_settings)

        org = OrganizationFactory.create(org_id="123", name="Test Org")
        networks = [
            NetworkFactory.create(
                network_id="N_123",
                name="Network1",
                product_types=["wireless", "switch"],
                org_id=org["id"],
            ),
            NetworkFactory.create(
                network_id="N_456",
                name="Network2",
                product_types=["appliance"],
                org_id=org["id"],
            ),
        ]

        mock_api.organizations.getOrganization = MagicMock(return_value=org)
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=networks)

        result = await service.run_discovery()

        mock_api.organizations.getOrganization.assert_called_once_with("123")
        mock_api.organizations.getOrganizationNetworks.assert_called_once_with(
            "123", total_pages="all"
        )
        assert len(result["organizations"]) == 1
        assert result["organizations"][0]["id"] == "123"

    @pytest.mark.asyncio
    async def test_run_discovery_with_single_org_error_shape(self, mock_api, mock_settings):
        """A getOrganization response shaped like an SDK exhausted-retry error is validated.

        The SDK can return a dict with an "errors" key after retries are exhausted, instead
        of raising. Without validate_response_format wrapping, this bogus dict would flow
        through as if it were a real organization ({}.get("id", "") -> "", masking the
        failure). It must instead be treated as a failure to fetch discovery data.
        """
        mock_settings.meraki.org_id = "123"
        service = DiscoveryService(api=mock_api, settings=mock_settings)

        mock_api.organizations.getOrganization = MagicMock(
            return_value={"errors": ["Invalid API key"]}
        )

        result = await service.run_discovery()

        mock_api.organizations.getOrganization.assert_called_once_with("123")
        assert result["organizations"] == []
        assert "discovery_failed" in result["errors"]

    @pytest.mark.asyncio
    async def test_run_discovery_with_multiple_orgs(self, discovery_service, mock_api):
        """Test discovery with multiple organizations."""
        orgs = [
            OrganizationFactory.create(org_id="123", name="Org1"),
            OrganizationFactory.create(org_id="456", name="Org2"),
        ]
        network = NetworkFactory.create(
            network_id="N_123",
            name="Network1",
            product_types=["wireless"],
        )

        mock_api.organizations.getOrganizations = MagicMock(return_value=orgs)
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=[network])

        await discovery_service.run_discovery()

        mock_api.organizations.getOrganizations.assert_called_once()
        assert mock_api.organizations.getOrganizationNetworks.call_count == 2

    @pytest.mark.asyncio
    async def test_discovery_handles_network_fetch_failure(self, discovery_service, mock_api):
        """Test handling of network fetch failures."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        mock_api.organizations.getOrganizations = MagicMock(return_value=[org])
        mock_api.organizations.getOrganizationNetworks = MagicMock(
            side_effect=Exception("Network error")
        )

        result = await discovery_service.run_discovery()

        mock_api.organizations.getOrganizationNetworks.assert_called_once()
        assert "123: networks_fetch_failed" in result["errors"]

    @pytest.mark.asyncio
    async def test_discovery_handles_complete_failure(self, discovery_service, mock_api):
        """Test handling of complete discovery failure."""
        mock_api.organizations.getOrganizations = MagicMock(
            side_effect=Exception("Authentication failed")
        )

        result = await discovery_service.run_discovery()

        mock_api.organizations.getOrganizations.assert_called_once()
        assert "discovery_failed" in result["errors"]

    @pytest.mark.asyncio
    async def test_discovery_counts_products(self, discovery_service, mock_api):
        """Test that discovery correctly counts product types from networks."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        networks = [
            NetworkFactory.create(
                network_id="N_1",
                name="Net1",
                product_types=["wireless", "switch"],
                org_id=org["id"],
            ),
            NetworkFactory.create(
                network_id="N_2",
                name="Net2",
                product_types=["wireless"],
                org_id=org["id"],
            ),
            NetworkFactory.create(
                network_id="N_3",
                name="Net3",
                product_types=["appliance", "switch"],
                org_id=org["id"],
            ),
        ]

        mock_api.organizations.getOrganizations = MagicMock(return_value=[org])
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=networks)

        result = await discovery_service.run_discovery()

        mock_api.organizations.getOrganizationNetworks.assert_called_once()
        assert result["networks"]["123"]["count"] == 3
        assert result["networks"]["123"]["product_types"]["wireless"] == 2
        assert result["networks"]["123"]["product_types"]["switch"] == 2
        assert result["networks"]["123"]["product_types"]["appliance"] == 1

    @pytest.mark.asyncio
    async def test_discovery_returns_summary_structure(self, discovery_service, mock_api):
        """Test that discovery returns proper summary structure."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        mock_api.organizations.getOrganizations = MagicMock(return_value=[org])
        mock_api.organizations.getOrganizationNetworks = MagicMock(return_value=[])

        result = await discovery_service.run_discovery()

        assert "organizations" in result
        assert "networks" in result
        assert "errors" in result
        assert len(result["organizations"]) == 1
        assert result["organizations"][0]["name"] == "Test Org"


class TestResolveOrgId:
    """Tests for the single-org contract resolver (#585)."""

    @pytest.mark.asyncio
    async def test_uses_configured_org_without_listing(self, mock_api, mock_settings):
        """When org_id is set, use it as-is and never call getOrganizations."""
        mock_settings.meraki.org_id = "123"
        mock_api.organizations.getOrganizations = MagicMock()

        resolved = await resolve_org_id(mock_api, mock_settings)

        assert resolved == "123"
        mock_api.organizations.getOrganizations.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_selects_single_visible_org(self, mock_api, mock_settings):
        """org_id unset + exactly one visible org -> auto-select and write back."""
        mock_settings.meraki.org_id = None
        org = OrganizationFactory.create(org_id="999", name="Solo Org")
        mock_api.organizations.getOrganizations = MagicMock(return_value=[org])

        resolved = await resolve_org_id(mock_api, mock_settings)

        assert resolved == "999"
        assert mock_settings.meraki.org_id == "999"
        mock_api.organizations.getOrganizations.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_org_fails_fast_listing_orgs(self, mock_api, mock_settings):
        """org_id unset + several visible orgs -> fail fast listing them."""
        mock_settings.meraki.org_id = None
        orgs = [
            OrganizationFactory.create(org_id="111", name="Alpha"),
            OrganizationFactory.create(org_id="222", name="Beta"),
        ]
        mock_api.organizations.getOrganizations = MagicMock(return_value=orgs)

        with pytest.raises(OrgResolutionError) as exc_info:
            await resolve_org_id(mock_api, mock_settings)

        message = str(exc_info.value)
        # Lists every visible org (id + name).
        assert "111" in message and "Alpha" in message
        assert "222" in message and "Beta" in message
        # Points at the config key and the sharding / Helm multi-instance path.
        assert "ORG_ID" in message
        assert "shard" in message.lower()
        assert "scaling-guide" in message or "Helm" in message
        # Must not silently pick one.
        assert mock_settings.meraki.org_id is None

    @pytest.mark.asyncio
    async def test_no_visible_orgs_fails_fast(self, mock_api, mock_settings):
        """org_id unset + zero visible orgs -> fail fast."""
        mock_settings.meraki.org_id = None
        mock_api.organizations.getOrganizations = MagicMock(return_value=[])

        with pytest.raises(OrgResolutionError):
            await resolve_org_id(mock_api, mock_settings)

    @pytest.mark.asyncio
    async def test_error_shaped_org_list_fails_fast(self, mock_api, mock_settings):
        """A getOrganizations SDK exhausted-retry error shape is not treated as orgs."""
        mock_settings.meraki.org_id = None
        mock_api.organizations.getOrganizations = MagicMock(
            return_value={"errors": ["Invalid API key"]}
        )

        with pytest.raises(Exception):  # noqa: B017 - RetryableAPIError/DataValidationError
            await resolve_org_id(mock_api, mock_settings)


class TestSingleOrgStartup:
    """Startup-wiring test: the resolver aborts app startup on an ambiguous key."""

    @pytest.mark.asyncio
    async def test_lifespan_aborts_on_multi_org_key(self, monkeypatch):
        """Entering the app lifespan with a multi-org key and no org_id raises.

        This proves the resolver is wired into startup BEFORE the server serves,
        so a multi-org key fails fast (aborting process startup) rather than
        polling an arbitrary org.
        """
        from pydantic import SecretStr

        from meraki_dashboard_exporter.app import ExporterApp
        from meraki_dashboard_exporter.core.config_models import MerakiSettings

        settings = Settings(meraki=MerakiSettings(api_key=SecretStr("a" * 40)))
        assert settings.meraki.org_id is None

        exporter = ExporterApp(settings)

        # Feed the resolver a multi-org list without any real network call by
        # priming the lazily-created SDK client.
        fake_api = MagicMock()
        fake_api.organizations.getOrganizations = MagicMock(
            return_value=[
                OrganizationFactory.create(org_id="1", name="A"),
                OrganizationFactory.create(org_id="2", name="B"),
            ]
        )
        exporter.client._api = fake_api

        app = exporter.create_app()

        with pytest.raises(OrgResolutionError):
            async with exporter.lifespan(app):
                pass  # pragma: no cover - startup must abort before yield
