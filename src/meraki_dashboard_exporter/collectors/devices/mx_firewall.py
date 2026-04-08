"""MX Firewall & Security Policy collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import MXMetricName
from ...core.error_handling import ErrorCategory, with_error_handling
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...core.config import Settings

logger = get_logger(__name__)


class MXFirewallCollector(SubCollectorMixin):
    """Collector for MX firewall rules and security policy metrics.

    Collects L3 and L7 firewall rule counts per network, plus the default
    policy setting for each appliance network. Uses SLOW tier (900s) as
    firewall configuration changes infrequently.
    """

    def __init__(self, parent: Any) -> None:
        """Initialize MX firewall collector.

        Parameters
        ----------
        parent : Any
            Parent collector instance (MXCollector) that exposes
            ``_create_gauge``, ``_set_metric``, ``api``, and ``settings``.

        """
        self.parent = parent
        self.api: DashboardAPI = parent.api
        self.settings: Settings = parent.settings
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize firewall-related Prometheus gauge metrics."""
        self._firewall_rules_total = self.parent._create_gauge(
            MXMetricName.MX_FIREWALL_RULES_TOTAL,
            "Total number of user-defined firewall rules by type (excludes default rule)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.RULE_TYPE,
            ],
        )
        self._firewall_default_policy = self.parent._create_gauge(
            MXMetricName.MX_FIREWALL_DEFAULT_POLICY,
            "Firewall default policy for L3 rules (1=allow, 0=deny)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )
        self._security_events_total = self.parent._create_gauge(
            MXMetricName.MX_SECURITY_EVENTS_TOTAL,
            "Total security events by type (reserved for future use)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.EVENT_TYPE,
            ],
        )

    @log_api_call("getNetworkApplianceFirewallL3FirewallRules")
    @with_error_handling(
        operation="Collect MX firewall rules",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_for_network(
        self,
        org_id: str,
        org_name: str,
        network_id: str,
        network_name: str,
    ) -> None:
        """Collect firewall rule counts and default policy for a single network.

        Fetches L3 and L7 firewall rules for the given appliance network.
        The last rule in the L3 rule list is always the default rule and is
        excluded from the user-defined rule count.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        network_id : str
            Network ID for the appliance network.
        network_name : str
            Human-readable network name.

        """
        base_labels = {
            LabelName.ORG_ID: org_id,
            LabelName.ORG_NAME: org_name,
            LabelName.NETWORK_ID: network_id,
            LabelName.NETWORK_NAME: network_name,
        }

        # L3 rules
        self._track_api_call("getNetworkApplianceFirewallL3FirewallRules")
        l3_response = await asyncio.to_thread(
            self.api.appliance.getNetworkApplianceFirewallL3FirewallRules,
            network_id,
        )
        l3_rules: list[dict[str, Any]] = l3_response.get("rules", []) if l3_response else []

        # The last rule is always the built-in default rule; exclude it from the count
        user_l3_rules = [r for r in l3_rules if r.get("comment", "") != "Default rule"]

        self.parent._set_metric(
            self._firewall_rules_total,
            {**base_labels, LabelName.RULE_TYPE: "L3"},
            float(len(user_l3_rules)),
        )

        # Default policy: determined from the last rule's policy field
        if l3_rules:
            default_rule = l3_rules[-1]
            default_policy = default_rule.get("policy", "deny")
            self.parent._set_metric(
                self._firewall_default_policy,
                base_labels,
                1.0 if default_policy == "allow" else 0.0,
            )

        # L7 rules
        self._track_api_call("getNetworkApplianceFirewallL7FirewallRules")
        l7_response = await asyncio.to_thread(
            self.api.appliance.getNetworkApplianceFirewallL7FirewallRules,
            network_id,
        )
        l7_rules: list[dict[str, Any]] = l7_response.get("rules", []) if l7_response else []

        self.parent._set_metric(
            self._firewall_rules_total,
            {**base_labels, LabelName.RULE_TYPE: "L7"},
            float(len(l7_rules)),
        )

        logger.debug(
            "Collected firewall rules",
            org_id=org_id,
            network_id=network_id,
            l3_user_rules=len(user_l3_rules),
            l7_rules=len(l7_rules),
        )
