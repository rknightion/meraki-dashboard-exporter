"""Configuration data collector for slow-changing settings."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, cast

from ..core.batch_processing import process_in_batches_with_errors
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
            OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_SECONDS,
            "Seconds before password expires (0 if not set)",
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
            OrgMetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_SECONDS,
            "Seconds before idle timeout (0 if not set)",
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
            OrgMetricName.ORG_CONFIGURATION_CHANGES_COUNT,
            "Number of configuration changes observed in the last 24 hours (fetch timespan=86400s)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        # Admin accounts & 2FA/SSO posture (aggregated, no per-admin PII)
        self._org_admins_total = self._create_gauge(
            OrgMetricName.ORG_ADMINS,
            "Number of org dashboard admins by authentication method and account status",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.AUTHENTICATION_METHOD,
                LabelName.ACCOUNT_STATUS,
            ],
        )

        self._org_admins_two_factor_enabled_total = self._create_gauge(
            OrgMetricName.ORG_ADMINS_TWO_FACTOR_ENABLED,
            "Number of org dashboard admins with two-factor auth enabled",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

    async def _get_organizations(self) -> list[dict[str, Any]]:
        """Get organizations from inventory cache or direct API.

        Uses inventory cache if available, otherwise falls back to direct API call.

        Returns
        -------
        list[dict[str, Any]]
            List of organization data.

        """
        if not self.inventory:
            logger.debug("Inventory not available, fetching organizations directly")
            return await self._fetch_organizations_direct() or []
        return await self.inventory.get_organizations()

    async def _collect_impl(self) -> None:
        """Collect configuration metrics."""
        start_time = time.time()
        metrics_collected = 0
        api_calls_made = 0

        try:
            # Get organizations from cache or API
            organizations = await self._get_organizations()
            if not organizations:
                logger.warning("No organizations found for config collection")
                return
            # Only count as API call if we didn't use cache
            if not self.inventory:
                api_calls_made += 1

            # Collect metrics for each organization with bounded concurrency
            # (never raw asyncio.gather) so we respect the API concurrency budget
            # while still collecting per-org errors (F-016).
            results = await process_in_batches_with_errors(
                organizations,
                self._collect_org_config,
                batch_size=self.settings.api.concurrency_limit,
                delay_between_batches=0.0,
                item_description="organization",
                error_context_func=lambda org: {
                    "org_id": org.get("id"),
                    "org_name": org.get("name"),
                },
            )

            # Count successful collections
            for _org, result in results:
                if not isinstance(result, Exception):
                    # Each org makes 3 API calls (login security + admins + config changes)
                    api_calls_made += 3

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
    async def _fetch_organizations_direct(self) -> list[dict[str, Any]] | None:
        """Fetch organizations directly from API (fallback when inventory unavailable).

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

            logger.debug("Collecting admin accounts", org_id=org_id)
            await self._collect_admins(org_id, org_name)

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
                # Normalize the SDK exhausted-retry error shape so an error-shaped
                # dict raises instead of silently emitting false zeros (F-034).
                security = validate_response_format(
                    security,
                    expected_type=dict,
                    operation="getOrganizationLoginSecurity",
                )

            # Password expiration
            self._login_security_password_expiration_enabled.labels(org_id, org_name).set(
                1 if security.get("enforcePasswordExpiration", False) else 0
            )

            # API value is in days; convert to seconds (x86400) for the renamed
            # meraki_org_login_security_password_expiration_seconds (issue #531).
            self._login_security_password_expiration_days.labels(org_id, org_name).set(
                (security.get("passwordExpirationDays") or 0) * 86400
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

            # API value is in minutes; convert to seconds (x60) for the renamed
            # meraki_org_login_security_idle_timeout_seconds (issue #531).
            self._login_security_idle_timeout_minutes.labels(org_id, org_name).set(
                (security.get("idleTimeoutMinutes") or 0) * 60
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

    # Known values as of the M3 roadmap spec; any unrecognized value observed on an
    # admin record is still counted (the pre-zero pass just won't have covered it).
    _KNOWN_AUTHENTICATION_METHODS: tuple[str, ...] = ("Email", "Cisco SecureX Sign-On")
    _KNOWN_ACCOUNT_STATUSES: tuple[str, ...] = ("ok", "locked", "pending", "unverified")

    @log_api_call("getOrganizationAdmins")
    async def _collect_admins(self, org_id: str, org_name: str) -> None:
        """Collect admin account & 2FA/SSO posture metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id, org_name=org_name):
                admins = await asyncio.to_thread(
                    self.api.organizations.getOrganizationAdmins,
                    org_id,
                )
                admins = validate_response_format(
                    admins, expected_type=list, operation="getOrganizationAdmins"
                )

            # Pre-zero the full bounded cross product so a combo that drops to zero
            # this cycle is reported as 0 rather than left stale or missing.
            for auth_method in self._KNOWN_AUTHENTICATION_METHODS:
                for account_status in self._KNOWN_ACCOUNT_STATUSES:
                    self._set_metric(
                        self._org_admins_total,
                        {
                            LabelName.ORG_ID: org_id,
                            LabelName.ORG_NAME: org_name,
                            LabelName.AUTHENTICATION_METHOD: auth_method,
                            LabelName.ACCOUNT_STATUS: account_status,
                        },
                        0,
                    )

            counts: dict[tuple[str, str], int] = {}
            two_factor_count = 0

            for admin in admins:
                auth_method = admin.get("authenticationMethod", "")
                account_status = admin.get("accountStatus", "")
                key = (auth_method, account_status)
                counts[key] = counts.get(key, 0) + 1

                if admin.get("twoFactorAuthEnabled", False):
                    two_factor_count += 1

            for (auth_method, account_status), count in counts.items():
                self._set_metric(
                    self._org_admins_total,
                    {
                        LabelName.ORG_ID: org_id,
                        LabelName.ORG_NAME: org_name,
                        LabelName.AUTHENTICATION_METHOD: auth_method,
                        LabelName.ACCOUNT_STATUS: account_status,
                    },
                    count,
                )

            self._set_metric(
                self._org_admins_two_factor_enabled_total,
                {LabelName.ORG_ID: org_id, LabelName.ORG_NAME: org_name},
                two_factor_count,
            )

            logger.debug(
                "Successfully collected admin account metrics",
                org_id=org_id,
                admin_count=len(admins),
                two_factor_count=two_factor_count,
            )

        except Exception:
            logger.exception(
                "Failed to collect admin account metrics",
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
                # Normalize the SDK exhausted-retry error shape so an error-shaped
                # dict raises instead of being counted as zero changes (F-034).
                config_changes = validate_response_format(
                    config_changes,
                    expected_type=list,
                    operation="getOrganizationConfigurationChanges",
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
