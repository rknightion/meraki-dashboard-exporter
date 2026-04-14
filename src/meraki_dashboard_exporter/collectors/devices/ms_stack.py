"""MS Switch Stack health collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.async_utils import ManagedTaskGroup
from ...core.constants.metrics_constants import MSMetricName
from ...core.error_handling import ErrorCategory, with_error_handling
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.metrics import LabelName
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...core.config import Settings

logger = get_logger(__name__)


class MSStackCollector(SubCollectorMixin):
    """Collector for MS switch stack health metrics.

    Collects per-stack membership and member count metrics by iterating over
    all networks in the organization and fetching switch stack data.

    Hardware health metrics (PSU/fan/temperature) are deferred pending
    Meraki API investigation.
    """

    def __init__(self, parent: Any) -> None:
        """Initialize the MS stack collector.

        Parameters
        ----------
        parent : Any
            Parent collector providing shared metrics and helpers.

        """
        self.parent = parent
        self.api: DashboardAPI = parent.api
        self.settings: Settings = parent.settings
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize stack-specific metrics."""
        self._stack_member_status = self.parent._create_gauge(
            MSMetricName.MS_STACK_MEMBER_STATUS,
            "Switch stack member status (1=present/online, 0=absent/offline)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.STACK_ID,
                LabelName.SERIAL,
                LabelName.ROLE,
            ],
        )
        self._stack_members_total = self.parent._create_gauge(
            MSMetricName.MS_STACK_MEMBERS_TOTAL,
            "Total number of members in switch stack",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.STACK_ID,
            ],
        )

    @log_api_call("getNetworkSwitchStacks")
    @with_error_handling(
        operation="Collect switch stack metrics for network",
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
        """Collect stack metrics for a single network.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        network_id : str
            Network ID.
        network_name : str
            Network name.

        """
        self._track_api_call("getNetworkSwitchStacks")

        with LogContext(org_id=org_id, network_id=network_id):
            stacks = await asyncio.to_thread(
                self.api.switch.getNetworkSwitchStacks,
                network_id,
            )

        if not isinstance(stacks, list):
            logger.warning(
                "Unexpected response format for getNetworkSwitchStacks",
                network_id=network_id,
                response_type=type(stacks).__name__,
            )
            return

        logger.debug(
            "Fetched switch stacks for network",
            network_id=network_id,
            stack_count=len(stacks),
        )

        for stack in stacks:
            stack_id = stack.get("id", "")
            serials: list[str] = stack.get("serials", [])

            if not stack_id:
                logger.debug("Skipping stack with missing id", network_id=network_id)
                continue

            # Total member count for the stack
            self._stack_members_total.labels(
                org_id=org_id,
                org_name=org_name,
                network_id=network_id,
                network_name=network_name,
                stack_id=stack_id,
            ).set(len(serials))

            # Per-member status — first serial is treated as primary
            for i, serial in enumerate(serials):
                role = "primary" if i == 0 else "member"
                self._stack_member_status.labels(
                    org_id=org_id,
                    org_name=org_name,
                    network_id=network_id,
                    network_name=network_name,
                    stack_id=stack_id,
                    serial=serial,
                    role=role,
                ).set(1)  # Presence in stack response means the switch is online/active

    async def collect_for_org(
        self,
        org_id: str,
        org_name: str,
        networks: list[dict[str, Any]],
    ) -> None:
        """Collect stack metrics for all switch networks in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        networks : list[dict[str, Any]]
            All networks for the organization (will be filtered to switch networks).

        """
        switch_networks = [n for n in networks if "switch" in n.get("productTypes", [])]

        logger.debug(
            "Collecting stack metrics for switch networks",
            org_id=org_id,
            switch_network_count=len(switch_networks),
        )

        async with ManagedTaskGroup(
            name="ms_stack_networks",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for network in switch_networks:
                network_id = network.get("id", "")
                network_name = network.get("name", network_id)
                if not network_id:
                    continue
                await group.create_task(
                    self.collect_for_network(org_id, org_name, network_id, network_name),
                    name=f"stack_{network_id}",
                )
