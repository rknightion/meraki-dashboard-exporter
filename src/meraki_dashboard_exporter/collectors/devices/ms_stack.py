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
from ...core.scheduler import EndpointGroupName
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
                LabelName.NETWORK_ID,
                LabelName.STACK_ID,
                LabelName.SERIAL,
                LabelName.ROLE,
            ],
        )
        self._stack_members_total = self.parent._create_gauge(
            MSMetricName.MS_STACK_MEMBERS,
            "Number of members in switch stack",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
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

        # #617: per-network fetch inside the collect_for_org fan-out; the group
        # gate lives on collect_for_org (once per cycle). Thread the MS_STACKS
        # solved TTL onto every emission here.
        stacks_ttl = self.parent._group_ttl_seconds(EndpointGroupName.MS_STACKS)

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
            members: list[dict[str, Any]] = stack.get("members") or []
            serials: list[str] = stack.get("serials", [])

            if not stack_id:
                logger.debug("Skipping stack with missing id", network_id=network_id)
                continue

            # Total member count for the stack — prefer the members array (has
            # per-member identity/role); fall back to serials for older/edge
            # responses that only include the plain serial list.
            #
            # Emit via ``parent._set_metric`` (not raw ``.labels().set()``) so
            # these series are tracked by the MetricExpirationManager and expire
            # when a member/stack is removed instead of lingering forever (F-175).
            self.parent._set_metric(
                self._stack_members_total,
                {
                    "org_id": org_id,
                    "network_id": network_id,
                    "stack_id": stack_id,
                },
                len(members) if members else len(serials),
                MSMetricName.MS_STACK_MEMBERS.value,
                ttl_seconds=stacks_ttl,
            )

            if members:
                # Per-member status using the API's own role (active/member/standby).
                for member in members:
                    serial = member.get("serial", "")
                    role = member.get("role", "")
                    # Presence in stack response means the switch is online/active
                    self.parent._set_metric(
                        self._stack_member_status,
                        {
                            "org_id": org_id,
                            "network_id": network_id,
                            "stack_id": stack_id,
                            "serial": serial,
                            "role": role,
                        },
                        1,
                        MSMetricName.MS_STACK_MEMBER_STATUS.value,
                        ttl_seconds=stacks_ttl,
                    )
            else:
                # Defensive fallback for responses without a members array:
                # positionally treat the first serial as primary.
                for i, serial in enumerate(serials):
                    role = "primary" if i == 0 else "member"
                    # Presence in stack response means the switch is online/active
                    self.parent._set_metric(
                        self._stack_member_status,
                        {
                            "org_id": org_id,
                            "network_id": network_id,
                            "stack_id": stack_id,
                            "serial": serial,
                            "role": role,
                        },
                        1,
                        MSMetricName.MS_STACK_MEMBER_STATUS.value,
                        ttl_seconds=stacks_ttl,
                    )

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
        # #617 gate: consult MS_STACKS once per cycle BEFORE the per-network
        # fan-out (a mark_ran inside collect_for_network would skip the rest of
        # the batch); mark_ran after the fan-out completes.
        if not self.parent._should_run_group(EndpointGroupName.MS_STACKS):
            return

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

        self.parent._mark_group_ran(EndpointGroupName.MS_STACKS)
