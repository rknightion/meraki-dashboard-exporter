"""Configuration data collector for slow-changing settings."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, cast

from ..core.collector import MetricCollector
from ..core.constants import OrgMetricName, UpdateTier
from ..core.domain_models import ConfigurationChange
from ..core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call
from ..core.logging_helpers import LogContext, log_metric_collection_summary
from ..core.metrics import LabelName
from ..core.registry import register_collector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


@register_collector(UpdateTier.SLOW)
class ConfigCollector(MetricCollector):
    """Collector for configuration and security settings."""

    def _initialize_metrics(self) -> None:
        """Initialize configuration metrics."""
        # Login security metrics
        self._login_security_password_expiration_enabled = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_ENABLED,
            "Whether password expiration is enforced (1=enabled, 0=disabled)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_password_expiration_days = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_DAYS,
            "Number of days before password expires (0 if not set)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_different_passwords_enabled = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_ENABLED,
            "Whether different passwords are enforced (1=enabled, 0=disabled)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_different_passwords_count = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_COUNT,
            "Number of different passwords required (0 if not set)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_strong_passwords_enabled = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_STRONG_PASSWORDS_ENABLED,
            "Whether strong passwords are enforced (1=enabled, 0=disabled)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_minimum_password_length = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_MINIMUM_PASSWORD_LENGTH,
            "Minimum password length required",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_account_lockout_enabled = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ENABLED,
            "Whether account lockout is enforced (1=enabled, 0=disabled)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_account_lockout_attempts = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ATTEMPTS,
            "Number of failed login attempts before lockout (0 if not set)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_idle_timeout_enabled = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_ENABLED,
            "Whether idle timeout is enforced (1=enabled, 0=disabled)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_idle_timeout_minutes = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_MINUTES,
            "Minutes before idle timeout (0 if not set)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_two_factor_enabled = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_TWO_FACTOR_ENABLED,
            "Whether two-factor authentication is enforced (1=enabled, 0=disabled)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_ip_ranges_enabled = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_IP_RANGES_ENABLED,
            "Whether login IP ranges are enforced (1=enabled, 0=disabled)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._login_security_api_ip_restrictions_enabled = self._create_gauge(
            OrgMetricName.ORG_LOGIN_SECURITY_API_IP_RESTRICTIONS_ENABLED,
            "Whether API key IP restrictions are enabled (1=enabled, 0=disabled)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        # Configuration change metrics
        self._configuration_changes_total = self._create_gauge(
            OrgMetricName.ORG_CONFIGURATION_CHANGES_TOTAL,
            "Total number of configuration changes in the last 24 hours",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

    async def _collect_impl(self) -> None:
        """Collect configuration metrics."""
        start_time = time.time()
        metrics_collected = 0
        api_calls_made = 0

        try:
            # Get organizations with error handling
            organizations = await self._fetch_organizations()
            if not organizations:
                logger.warning("No organizations found for config collection")
                return
            api_calls_made += 1

            # Collect metrics for each organization
            tasks = [self._collect_org_config(org) for org in organizations]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successful collections
            for result in results:
                if not isinstance(result, Exception):
                    # Each org makes 2 API calls (login security + config changes)
                    api_calls_made += 2

            # Log collection summary
            duration = time.time() - start_time
            log_metric_collection_summary(
                "ConfigCollector",
                metrics_collected=metrics_collected,
                duration_seconds=duration,
                organizations_processed=len(organizations),
                api_calls_made=api_calls_made,
            )

        except Exception:
            logger.exception("Failed to collect configuration metrics")

    @log_api_call("getOrganization")
    @with_error_handling(
        operation="Fetch organizations",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_organizations(self) -> list[dict[str, Any]] | None:
        """Fetch organizations for config collection.

        Returns
        -------
        list[dict[str, Any]] | None
            List of organizations or None on error.

        """
        if self.settings.meraki.org_id:
            # Single organization
            org = await asyncio.to_thread(
                self.api.organizations.getOrganization,
                self.settings.meraki.org_id,
            )
            return [org]
        else:
            # All accessible organizations
            organizations = await asyncio.to_thread(self.api.organizations.getOrganizations)
            organizations = validate_response_format(
                organizations, expected_type=list, operation="getOrganizations"
            )
            return cast(list[dict[str, Any]], organizations)

    @with_error_handling(
        operation="Collect organization config",
        continue_on_error=True,
    )
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

    @log_api_call("getOrganizationLoginSecurity")
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
            with LogContext(org_id=org_id, org_name=org_name):
                security = await asyncio.to_thread(
                    self.api.organizations.getOrganizationLoginSecurity,
                    org_id,
                )

            # Password expiration
            self._login_security_password_expiration_enabled.labels(org_id, org_name).set(
                1 if security.get("enforcePasswordExpiration", False) else 0
            )

            self._login_security_password_expiration_days.labels(org_id, org_name).set(
                security.get("passwordExpirationDays") or 0
            )

            # Different passwords
            self._login_security_different_passwords_enabled.labels(org_id, org_name).set(
                1 if security.get("enforceDifferentPasswords", False) else 0
            )

            self._login_security_different_passwords_count.labels(org_id, org_name).set(
                security.get("numDifferentPasswords") or 0
            )

            # Strong passwords
            self._login_security_strong_passwords_enabled.labels(org_id, org_name).set(
                1 if security.get("enforceStrongPasswords", False) else 0
            )

            self._login_security_minimum_password_length.labels(org_id, org_name).set(
                security.get("minimumPasswordLength") or 0
            )

            # Account lockout
            self._login_security_account_lockout_enabled.labels(org_id, org_name).set(
                1 if security.get("enforceAccountLockout", False) else 0
            )

            self._login_security_account_lockout_attempts.labels(org_id, org_name).set(
                security.get("accountLockoutAttempts") or 0
            )

            # Idle timeout
            self._login_security_idle_timeout_enabled.labels(org_id, org_name).set(
                1 if security.get("enforceIdleTimeout", False) else 0
            )

            self._login_security_idle_timeout_minutes.labels(org_id, org_name).set(
                security.get("idleTimeoutMinutes") or 0
            )

            # Two-factor auth
            self._login_security_two_factor_enabled.labels(org_id, org_name).set(
                1 if security.get("enforceTwoFactorAuth", False) else 0
            )

            # IP ranges
            self._login_security_ip_ranges_enabled.labels(org_id, org_name).set(
                1 if security.get("enforceLoginIpRanges", False) else 0
            )

            # API IP restrictions
            api_auth = security.get("apiAuthentication", {})
            ip_restrictions = api_auth.get("ipRestrictionsForKeys", {})
            api_ip_enabled = ip_restrictions.get("enabled", False)

            self._login_security_api_ip_restrictions_enabled.labels(org_id, org_name).set(
                1 if api_ip_enabled else 0
            )

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

    @log_api_call("getOrganizationConfigurationChanges")
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
            with LogContext(org_id=org_id, org_name=org_name):
                # Get configuration changes for the last 24 hours
                config_changes = await asyncio.to_thread(
                    self.api.organizations.getOrganizationConfigurationChanges,
                    org_id,
                    timespan=86400,  # 24 hours in seconds
                    total_pages="all",
                )

            # Parse changes using domain model for validation
            parsed_changes = []
            if config_changes:
                for change in config_changes:
                    try:
                        parsed_change = ConfigurationChange(**change)
                        parsed_changes.append(parsed_change)
                    except Exception:
                        logger.debug("Failed to parse configuration change", change=change)
                        continue

            # Count the total number of valid changes
            change_count = len(parsed_changes)

            # Set the metric
            if self._configuration_changes_total:
                self._configuration_changes_total.labels(org_id, org_name).set(change_count)
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
                    self._configuration_changes_total.labels(org_id, org_name).set(0)
            else:
                logger.exception(
                    "Failed to collect configuration changes",
                    org_id=org_id,
                    org_name=org_name,
                )
