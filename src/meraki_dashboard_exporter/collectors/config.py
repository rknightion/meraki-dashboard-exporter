"""Configuration data collector for slow-changing settings."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.collector import MetricCollector
from ..core.constants import UpdateTier
from ..core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ConfigCollector(MetricCollector):
    """Collector for configuration and security settings."""

    # Configuration data updates infrequently
    update_tier: UpdateTier = UpdateTier.SLOW

    def _initialize_metrics(self) -> None:
        """Initialize configuration metrics."""
        # Login security metrics
        self._login_security_password_expiration_enabled = self._create_gauge(
            "meraki_org_login_security_password_expiration_enabled",
            "Whether password expiration is enforced (1=enabled, 0=disabled)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_password_expiration_days = self._create_gauge(
            "meraki_org_login_security_password_expiration_days",
            "Number of days before password expires (0 if not set)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_different_passwords_enabled = self._create_gauge(
            "meraki_org_login_security_different_passwords_enabled",
            "Whether different passwords are enforced (1=enabled, 0=disabled)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_different_passwords_count = self._create_gauge(
            "meraki_org_login_security_different_passwords_count",
            "Number of different passwords required (0 if not set)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_strong_passwords_enabled = self._create_gauge(
            "meraki_org_login_security_strong_passwords_enabled",
            "Whether strong passwords are enforced (1=enabled, 0=disabled)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_minimum_password_length = self._create_gauge(
            "meraki_org_login_security_minimum_password_length",
            "Minimum password length required",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_account_lockout_enabled = self._create_gauge(
            "meraki_org_login_security_account_lockout_enabled",
            "Whether account lockout is enforced (1=enabled, 0=disabled)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_account_lockout_attempts = self._create_gauge(
            "meraki_org_login_security_account_lockout_attempts",
            "Number of failed login attempts before lockout (0 if not set)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_idle_timeout_enabled = self._create_gauge(
            "meraki_org_login_security_idle_timeout_enabled",
            "Whether idle timeout is enforced (1=enabled, 0=disabled)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_idle_timeout_minutes = self._create_gauge(
            "meraki_org_login_security_idle_timeout_minutes",
            "Minutes before idle timeout (0 if not set)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_two_factor_enabled = self._create_gauge(
            "meraki_org_login_security_two_factor_enabled",
            "Whether two-factor authentication is enforced (1=enabled, 0=disabled)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_ip_ranges_enabled = self._create_gauge(
            "meraki_org_login_security_ip_ranges_enabled",
            "Whether login IP ranges are enforced (1=enabled, 0=disabled)",
            labelnames=["org_id", "org_name"],
        )

        self._login_security_api_ip_restrictions_enabled = self._create_gauge(
            "meraki_org_login_security_api_ip_restrictions_enabled",
            "Whether API key IP restrictions are enabled (1=enabled, 0=disabled)",
            labelnames=["org_id", "org_name"],
        )

        # Configuration change metrics
        self._configuration_changes_total = self._create_gauge(
            "meraki_org_configuration_changes_total",
            "Total number of configuration changes in the last 24 hours",
            labelnames=["org_id", "org_name"],
        )

    async def _collect_impl(self) -> None:
        """Collect configuration metrics."""
        try:
            # Get organizations
            if self.settings.org_id:
                # Single organization
                logger.debug("Fetching single organization", org_id=self.settings.org_id)
                self._track_api_call("getOrganization")
                org = await asyncio.to_thread(
                    self.api.organizations.getOrganization,
                    self.settings.org_id,
                )
                organizations = [org]
                logger.debug(
                    "Successfully fetched organization", org_name=org.get("name", "unknown")
                )
            else:
                # All accessible organizations
                logger.debug("Fetching all organizations for config collection")
                self._track_api_call("getOrganizations")
                organizations = await asyncio.to_thread(self.api.organizations.getOrganizations)
                logger.debug("Successfully fetched organizations", count=len(organizations))

            # Collect metrics for each organization
            tasks = [self._collect_org_config(org) for org in organizations]
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception:
            logger.exception("Failed to collect configuration metrics")

    async def _collect_org_config(self, org: dict[str, Any]) -> None:
        """Collect configuration for a specific organization.

        Parameters
        ----------
        org : dict[str, Any]
            Organization data.

        """
        org_id = org["id"]
        org_name = org["name"]

        try:
            logger.debug("Collecting login security configuration", org_id=org_id)
            await self._collect_login_security(org_id, org_name)

            logger.debug("Collecting configuration changes", org_id=org_id)
            await self._collect_configuration_changes(org_id, org_name)

        except Exception:
            logger.exception(
                "Failed to collect configuration for organization",
                org_id=org_id,
                org_name=org_name,
            )

    async def _collect_login_security(self, org_id: str, org_name: str) -> None:
        """Collect login security configuration.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            logger.debug("Fetching login security settings", org_id=org_id)
            self._track_api_call("getOrganizationLoginSecurity")
            security = await asyncio.to_thread(
                self.api.organizations.getOrganizationLoginSecurity,
                org_id,
            )
            logger.debug("Successfully fetched login security settings", org_id=org_id)

            # Password expiration
            self._login_security_password_expiration_enabled.labels(
                org_id=org_id, org_name=org_name
            ).set(1 if security.get("enforcePasswordExpiration", False) else 0)

            self._login_security_password_expiration_days.labels(
                org_id=org_id, org_name=org_name
            ).set(security.get("passwordExpirationDays") or 0)

            # Different passwords
            self._login_security_different_passwords_enabled.labels(
                org_id=org_id, org_name=org_name
            ).set(1 if security.get("enforceDifferentPasswords", False) else 0)

            self._login_security_different_passwords_count.labels(
                org_id=org_id, org_name=org_name
            ).set(security.get("numDifferentPasswords") or 0)

            # Strong passwords
            self._login_security_strong_passwords_enabled.labels(
                org_id=org_id, org_name=org_name
            ).set(1 if security.get("enforceStrongPasswords", False) else 0)

            self._login_security_minimum_password_length.labels(
                org_id=org_id, org_name=org_name
            ).set(security.get("minimumPasswordLength") or 0)

            # Account lockout
            self._login_security_account_lockout_enabled.labels(
                org_id=org_id, org_name=org_name
            ).set(1 if security.get("enforceAccountLockout", False) else 0)

            self._login_security_account_lockout_attempts.labels(
                org_id=org_id, org_name=org_name
            ).set(security.get("accountLockoutAttempts") or 0)

            # Idle timeout
            self._login_security_idle_timeout_enabled.labels(org_id=org_id, org_name=org_name).set(
                1 if security.get("enforceIdleTimeout", False) else 0
            )

            self._login_security_idle_timeout_minutes.labels(org_id=org_id, org_name=org_name).set(
                security.get("idleTimeoutMinutes") or 0
            )

            # Two-factor auth
            self._login_security_two_factor_enabled.labels(org_id=org_id, org_name=org_name).set(
                1 if security.get("enforceTwoFactorAuth", False) else 0
            )

            # IP ranges
            self._login_security_ip_ranges_enabled.labels(org_id=org_id, org_name=org_name).set(
                1 if security.get("enforceLoginIpRanges", False) else 0
            )

            # API IP restrictions
            api_auth = security.get("apiAuthentication", {})
            ip_restrictions = api_auth.get("ipRestrictionsForKeys", {})
            api_ip_enabled = ip_restrictions.get("enabled", False)

            self._login_security_api_ip_restrictions_enabled.labels(
                org_id=org_id, org_name=org_name
            ).set(1 if api_ip_enabled else 0)

            logger.debug(
                "Successfully collected login security metrics",
                org_id=org_id,
                password_expiration=security.get("enforcePasswordExpiration"),
                two_factor=security.get("enforceTwoFactorAuth"),
                api_ip_restrictions=api_ip_enabled,
            )

        except Exception:
            logger.exception(
                "Failed to collect login security metrics",
                org_id=org_id,
                org_name=org_name,
            )

    async def _collect_configuration_changes(self, org_id: str, org_name: str) -> None:
        """Collect configuration changes count for the last 24 hours.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            logger.debug("Fetching configuration changes", org_id=org_id)
            self._track_api_call("getOrganizationConfigurationChanges")

            # Get configuration changes for the last 24 hours
            config_changes = await asyncio.to_thread(
                self.api.organizations.getOrganizationConfigurationChanges,
                org_id,
                timespan=86400,  # 24 hours in seconds
                total_pages="all",
            )

            # Count the total number of changes
            change_count = len(config_changes) if config_changes else 0

            # Set the metric
            if self._configuration_changes_total:
                self._configuration_changes_total.labels(
                    org_id=org_id,
                    org_name=org_name,
                ).set(change_count)
                logger.debug(
                    "Successfully collected configuration changes",
                    org_id=org_id,
                    change_count=change_count,
                )
            else:
                logger.error("_configuration_changes_total metric not initialized")

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            error_str = str(e)
            if "400" in error_str or "404" in error_str or "Bad Request" in error_str:
                logger.debug(
                    "Configuration changes API not available",
                    org_id=org_id,
                    org_name=org_name,
                    error=error_str,
                )
                # Set metric to 0 when API is not available
                if self._configuration_changes_total:
                    self._configuration_changes_total.labels(
                        org_id=org_id,
                        org_name=org_name,
                    ).set(0)
            else:
                logger.exception(
                    "Failed to collect configuration changes",
                    org_id=org_id,
                    org_name=org_name,
                )
