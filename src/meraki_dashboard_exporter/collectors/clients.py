"""Client metrics collector for network-wide client data."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from ..core.api_helpers import create_api_helper
from ..core.api_models import NetworkClient
from ..core.collector import MetricCollector
from ..core.constants import ClientMetricName, UpdateTier
from ..core.error_handling import ErrorCategory, with_error_handling
from ..core.logging_decorators import log_api_call, log_collection_progress
from ..core.metrics import LabelName
from ..core.registry import register_collector
from ..services.client_store import ClientStore
from ..services.dns_resolver import DNSResolver

logger = structlog.get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class ClientsCollector(MetricCollector):
    """Collector for client-level metrics across all networks."""

    @property
    def is_active(self) -> bool:
        """Check if this collector is actively collecting metrics."""
        return getattr(self, "_enabled", False)

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize the clients collector.

        Parameters
        ----------
        *args : Any
            Positional arguments passed to parent.
        **kwargs : Any
            Keyword arguments passed to parent.

        """
        super().__init__(*args, **kwargs)

        # Check if client collection is enabled
        if not self.settings.clients.enabled:
            logger.info("Client data collection is disabled")
            self._enabled = False
            return

        self._enabled = True
        self.api_helper = create_api_helper(self)

        # Initialize services
        self.client_store = ClientStore(self.settings)
        self.dns_resolver = DNSResolver(self.settings)

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for client data."""
        # Skip metric initialization if collector is disabled
        if not self.settings.clients.enabled:
            return

        # Client status metric (1 = online, 0 = offline)
        self.client_status = self._create_gauge(
            ClientMetricName.CLIENT_STATUS,
            "Client online status (1 = online, 0 = offline)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.CLIENT_ID,
                LabelName.MAC,
                LabelName.DESCRIPTION,
                LabelName.HOSTNAME,
                LabelName.SSID,
            ],
        )

        # Client usage metrics - using Gauge since these are point-in-time measurements
        # that can go up or down (hourly usage windows from API)
        self.client_usage_sent = self._create_gauge(
            ClientMetricName.CLIENT_USAGE_SENT_KB,
            "Kilobytes sent by client in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.CLIENT_ID,
                LabelName.MAC,
                LabelName.DESCRIPTION,
                LabelName.HOSTNAME,
                LabelName.SSID,
            ],
        )

        self.client_usage_recv = self._create_gauge(
            ClientMetricName.CLIENT_USAGE_RECV_KB,
            "Kilobytes received by client in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.CLIENT_ID,
                LabelName.MAC,
                LabelName.DESCRIPTION,
                LabelName.HOSTNAME,
                LabelName.SSID,
            ],
        )

        self.client_usage_total = self._create_gauge(
            ClientMetricName.CLIENT_USAGE_TOTAL_KB,
            "Total kilobytes transferred by client in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.CLIENT_ID,
                LabelName.MAC,
                LabelName.DESCRIPTION,
                LabelName.HOSTNAME,
                LabelName.SSID,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect client metrics from all organizations and networks."""
        if not self._enabled:
            logger.debug("Client collection is disabled, skipping")
            return

        organizations = await self.api_helper.get_organizations()

        if not organizations:
            return

        for org in organizations:
            org_id = org["id"]
            org_name = org["name"]

            # Get all networks for the organization
            networks = await self.api_helper.get_organization_networks(org_id)

            if not networks:
                continue

            # Process networks directly without batching to avoid lambda issues
            # Since we're already processing one org at a time, this is fine
            await self._process_network_batch(org_id, org_name, networks)

    async def _process_network_batch(
        self,
        org_id: str,
        org_name: str,
        networks: list[Any],
    ) -> None:
        """Process a batch of networks for client collection.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        networks : list[Any]
            List of networks to process.

        """
        tasks = []
        for network in networks:
            task = self._collect_network_clients(
                org_id,
                org_name,
                network["id"],
                network["name"],
            )
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    @with_error_handling(
        operation="Collect network clients",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    @log_api_call("getNetworkClients")
    async def _collect_network_clients(
        self,
        org_id: str,
        org_name: str,
        network_id: str,
        network_name: str,
    ) -> None:
        """Collect client data for a specific network.

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
        logger.debug(
            "Collecting client data",
            org_id=org_id,
            org_name=org_name,
            network_id=network_id,
            network_name=network_name,
        )

        # Always fetch fresh data from API to get current status and usage
        # The cache is only used for hostname lookups, not for skipping API calls
        self._track_api_call("getNetworkClients")
        try:
            clients_data = await asyncio.to_thread(
                self.api.networks.getNetworkClients,
                network_id,
                timespan=3600,  # 1 hour as requested
                perPage=5000,  # Maximum allowed
                total_pages="all",
            )
        except Exception as e:
            logger.error(
                "Failed to fetch clients",
                org_id=org_id,
                network_id=network_id,
                network_name=network_name,
                error=str(e),
            )
            self._track_error(ErrorCategory.API_CLIENT_ERROR)
            return

        # Parse client data
        clients = [NetworkClient.model_validate(c) for c in clients_data]

        logger.info(
            "Fetched client data",
            org_id=org_id,
            network_id=network_id,
            network_name=network_name,
            client_count=len(clients),
        )

        # Prepare client data for DNS resolution
        client_data = [(c.id, c.ip, c.description) for c in clients]

        # Resolve hostnames with client tracking
        logger.debug(
            "Resolving hostnames for network",
            network_id=network_id,
            client_count=len(clients),
        )
        hostnames = await self.dns_resolver.resolve_multiple(client_data)

        # Update client store
        self.client_store.update_clients(
            network_id,
            clients,
            network_name=network_name,
            org_id=org_id,
            hostnames=hostnames,
        )

        # Update metrics
        await self._update_metrics(org_id, org_name, network_id, network_name, clients, hostnames)

    def _sanitize_label_value(self, value: str | None, max_length: int = 2048) -> str:
        """Sanitize a label value for Prometheus.

        Parameters
        ----------
        value : str | None
            Value to sanitize.
        max_length : int
            Maximum length for the label value.

        Returns
        -------
        str
            Sanitized value.

        """
        if not value:
            return ""

        # Replace characters not allowed in Prometheus labels with hyphen
        # Allowed: [a-zA-Z0-9_-]
        sanitized = ""
        for char in value:
            if char.isalnum() or char in "_- ":
                sanitized += char
            else:
                sanitized += "-"

        # Truncate to max length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        return sanitized

    def _determine_hostname(
        self,
        client: NetworkClient,
        resolved_hostname: str | None,
    ) -> str:
        """Determine the hostname to use for a client.

        Priority:
        1. Resolved hostname from DNS
        2. Client description (if not empty)
        3. Client IP address
        4. "unknown"

        Parameters
        ----------
        client : NetworkClient
            Client data.
        resolved_hostname : str | None
            Hostname resolved from DNS.

        Returns
        -------
        str
            Hostname to use.

        """
        # Priority 1: DNS resolved hostname
        if resolved_hostname:
            return resolved_hostname

        # Priority 2: Client description
        if client.description:
            return client.description

        # Priority 3: Client IP
        if client.ip:
            return client.ip

        # Priority 4: Fallback
        return "unknown"

    @log_collection_progress("clients")
    async def _update_metrics(
        self,
        org_id: str,
        org_name: str,
        network_id: str,
        network_name: str,
        clients: list[NetworkClient],
        hostnames: dict[str, str | None],
        current: int = 0,
        total: int = 0,
    ) -> None:
        """Update Prometheus metrics for clients.

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
        clients : list[NetworkClient]
            List of clients.
        hostnames : dict[str, str | None]
            Resolved hostnames by IP.
        current : int
            Current progress (for logging).
        total : int
            Total items (for logging).

        """
        for client in clients:
            # Get resolved hostname from DNS
            resolved_hostname = hostnames.get(client.ip) if client.ip else None

            # Determine final hostname using fallback logic
            hostname = self._determine_hostname(client, resolved_hostname)

            # Sanitize label values
            sanitized_hostname = self._sanitize_label_value(hostname)
            sanitized_description = self._sanitize_label_value(client.description)

            # Determine effective SSID
            ssid = client.ssid if client.recentDeviceConnection == "Wireless" else "Wired"

            # Common labels
            labels = {
                str(LabelName.ORG_ID): org_id,
                str(LabelName.ORG_NAME): org_name,
                str(LabelName.NETWORK_ID): network_id,
                str(LabelName.NETWORK_NAME): network_name,
                str(LabelName.CLIENT_ID): client.id,
                str(LabelName.MAC): client.mac,
                str(LabelName.DESCRIPTION): sanitized_description,
                str(LabelName.HOSTNAME): sanitized_hostname,
                str(LabelName.SSID): ssid or "Unknown",
            }

            # Set client status
            status_value = 1 if client.status == "Online" else 0
            self.client_status.labels(**labels).set(status_value)

            # Set usage metrics (as gauges - these are point-in-time measurements)
            if client.usage:
                sent_kb = client.usage.get("sent", 0)
                recv_kb = client.usage.get("recv", 0)
                total_kb = client.usage.get("total", 0)

                # Set gauge values
                self.client_usage_sent.labels(**labels).set(float(sent_kb))
                self.client_usage_recv.labels(**labels).set(float(recv_kb))
                self.client_usage_total.labels(**labels).set(float(total_kb))

            logger.debug(
                "Updated client metrics",
                client_id=client.id,
                mac=client.mac,
                description=client.description,
                hostname=hostname,
                status=client.status,
                ssid=ssid,
            )
