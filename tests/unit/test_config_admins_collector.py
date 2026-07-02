"""Tests for ConfigCollector admin accounts & 2FA/SSO posture (_collect_admins)."""

from __future__ import annotations

from unittest.mock import patch

from meraki_dashboard_exporter.collectors.config import ConfigCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import OrganizationFactory


def _admin(
    authentication_method: str = "Email",
    account_status: str = "ok",
    two_factor: bool = False,
    **overrides: object,
) -> dict[str, object]:
    """Build a minimal getOrganizationAdmins-shaped admin record."""
    admin = {
        "id": "admin_1",
        "name": "Test Admin",
        "email": "admin@example.com",
        "orgAccess": "full",
        "accountStatus": account_status,
        "twoFactorAuthEnabled": two_factor,
        "hasApiKey": False,
        "lastActive": "2026-06-01T00:00:00Z",
        "authenticationMethod": authentication_method,
    }
    admin.update(overrides)
    return admin


class TestConfigCollectorAdmins(BaseCollectorTest):
    """Test ConfigCollector._collect_admins behavior."""

    collector_class = ConfigCollector
    update_tier = UpdateTier.SLOW

    async def test_admins_grouped_by_auth_method_and_account_status(
        self, collector, mock_api_builder, metrics
    ):
        """Admins are counted per (authentication_method, account_status) combo."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        admins = [
            _admin(authentication_method="Email", account_status="ok", two_factor=True, id="a1"),
            _admin(authentication_method="Email", account_status="ok", two_factor=False, id="a2"),
            _admin(
                authentication_method="Cisco SecureX Sign-On",
                account_status="locked",
                two_factor=True,
                id="a3",
            ),
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAdmins", admins)
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        metrics.assert_gauge_value(
            "meraki_org_admins",
            2,
            org_id="123",
            authentication_method="Email",
            account_status="ok",
        )
        metrics.assert_gauge_value(
            "meraki_org_admins",
            1,
            org_id="123",
            authentication_method="Cisco SecureX Sign-On",
            account_status="locked",
        )

    async def test_two_factor_enabled_count(self, collector, mock_api_builder, metrics):
        """Two-factor gauge reflects only admins with twoFactorAuthEnabled True."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        admins = [
            _admin(two_factor=True, id="a1"),
            _admin(two_factor=True, id="a2"),
            _admin(two_factor=False, id="a3"),
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAdmins", admins)
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        metrics.assert_gauge_value(
            "meraki_org_admins_two_factor_enabled",
            2,
            org_id="123",
        )

    async def test_known_combo_prezeroed_when_absent(self, collector, mock_api_builder, metrics):
        """A known (auth_method, account_status) combo with no admins reports 0, not missing."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Only "Email"/"ok" admins present; all other known combos should still be
        # pre-zeroed so a combo that drops to zero this cycle doesn't linger stale
        # or vanish from the series.
        admins = [_admin(authentication_method="Email", account_status="ok", id="a1")]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAdmins", admins)
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        metrics.assert_gauge_value(
            "meraki_org_admins",
            0,
            org_id="123",
            authentication_method="Cisco SecureX Sign-On",
            account_status="locked",
        )
        metrics.assert_gauge_value(
            "meraki_org_admins",
            0,
            org_id="123",
            authentication_method="Email",
            account_status="pending",
        )

    async def test_no_admins_still_zeroes_known_combos(self, collector, mock_api_builder, metrics):
        """An empty admins list still pre-zeroes the full bounded cross product."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAdmins", [])
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        metrics.assert_gauge_value(
            "meraki_org_admins",
            0,
            org_id="123",
            authentication_method="Email",
            account_status="ok",
        )
        metrics.assert_gauge_value(
            "meraki_org_admins_two_factor_enabled",
            0,
            org_id="123",
        )

    async def test_admin_metrics_routed_through_set_metric(
        self, collector, mock_api_builder, metrics
    ):
        """Admin metrics must emit via _set_metric for expiration tracking (F-011)."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        admins = [_admin(authentication_method="Email", account_status="ok", two_factor=True)]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAdmins", admins)
            .build()
        )
        collector.api = api

        with patch.object(collector, "_set_metric", wraps=collector._set_metric) as spy:
            await self.run_collector(collector)

        routed_metrics = {call.args[0] for call in spy.call_args_list}
        assert collector._org_admins_total in routed_metrics
        assert collector._org_admins_two_factor_enabled_total in routed_metrics

        # Values are still set correctly through the expiration-aware path.
        metrics.assert_gauge_value(
            "meraki_org_admins_two_factor_enabled",
            1,
            org_id="123",
        )

    async def test_admin_pii_fields_not_used_as_labels(self, collector, mock_api_builder, metrics):
        """Per-admin PII (name/email/id) must never appear as a label value."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        admins = [
            _admin(
                authentication_method="Email",
                account_status="ok",
                id="secret-admin-id",
                name="Sensitive Name",
                email="sensitive@example.com",
            )
        ]

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationAdmins", admins)
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        metric = metrics.get_metric("meraki_org_admins")
        for sample in metric.samples:
            label_values = sample.labels.values()
            assert "secret-admin-id" not in label_values
            assert "Sensitive Name" not in label_values
            assert "sensitive@example.com" not in label_values
            # Only the expected bounded label set is present.
            assert set(sample.labels.keys()) == {
                "org_id",
                "authentication_method",
                "account_status",
            }
