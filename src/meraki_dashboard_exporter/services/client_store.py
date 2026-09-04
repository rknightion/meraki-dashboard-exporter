"""Client data store for managing client information."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Any

import structlog

from ..core.api_models import NetworkClient
from ..core.config import Settings
from ..core.domain_models import ClientData

logger = structlog.get_logger(__name__)

_API_OWNED_CLIENT_FIELDS = frozenset(ClientData.model_fields) & frozenset(
    NetworkClient.model_fields
)


@dataclass(frozen=True)
class ClientPageSnapshot:
    """A bounded page of cached clients and the metadata needed to render it."""

    clients: list[ClientData]
    total_clients: int
    online_clients: int
    network_count: int
    page: int
    total_pages: int


class ClientStore:
    """In-memory store for client data with TTL support."""

    def __init__(self, settings: Settings):
        """Initialize client store.

        Parameters
        ----------
        settings : Settings
            Application settings.

        """
        self.settings = settings
        self.cache_ttl = settings.clients.cache_ttl
        self.max_clients_per_network = settings.clients.max_clients_per_network
        self.max_clients_total = settings.clients.max_clients_total

        # Store clients by network ID
        self._clients: dict[str, dict[str, ClientData]] = {}

        # Track last update time per network
        self._last_update: dict[str, float] = {}

        # Track network names for display
        self._network_names: dict[str, str] = {}

        # Track organization IDs for networks
        self._network_orgs: dict[str, str] = {}

        # Page snapshots run on a dedicated worker while collection mutates the
        # store on the event-loop thread. Keep each traversal and mutation
        # atomic so dictionary iterators never overlap a structural change.
        self._lock = RLock()

    def update_clients(
        self,
        network_id: str,
        clients: list[NetworkClient],
        network_name: str | None = None,
        org_id: str | None = None,
        hostnames: dict[str, str | None] | None = None,
        complete_snapshot: bool = False,
    ) -> None:
        """Update clients for a network.

        Parameters
        ----------
        network_id : str
            Network ID.
        clients : list[NetworkClient]
            List of client data from API.
        network_name : str | None
            Network name for display.
        org_id : str | None
            Organization ID.
        hostnames : dict[str, str | None] | None
            Resolved hostnames by IP address.
        complete_snapshot : bool
            Whether ``clients`` is the complete API result for this network.
            Only complete snapshots may remove clients absent from the result.

        """
        with self._lock:
            self._update_clients(
                network_id,
                clients,
                network_name=network_name,
                org_id=org_id,
                hostnames=hostnames,
                complete_snapshot=complete_snapshot,
            )

    def _update_clients(
        self,
        network_id: str,
        clients: list[NetworkClient],
        network_name: str | None = None,
        org_id: str | None = None,
        hostnames: dict[str, str | None] | None = None,
        complete_snapshot: bool = False,
    ) -> None:
        """Update one network while the caller holds ``_lock``."""
        if network_name is not None:
            self._network_names[network_id] = network_name
        if org_id is not None:
            self._network_orgs[network_id] = org_id

        # Inner client maps are copy-on-write. A page worker may retain a
        # published map after releasing ``_lock``; never mutate that map again.
        published_network_clients = self._clients.get(network_id, {})
        network_clients = published_network_clients.copy()
        updated_count = 0
        new_count = 0
        skipped_new_count = 0

        # Limit number of clients per network
        clients_to_process = clients[: self.max_clients_per_network]
        if len(clients) > self.max_clients_per_network:
            logger.warning(
                "Client limit exceeded for network",
                network_id=network_id,
                network_name=network_name,
                total_clients=len(clients),
                limit=self.max_clients_per_network,
            )

        # The store itself must also regard a per-network cap as incomplete,
        # even if a caller mistakenly marks it complete. Reconcile before
        # calculating global capacity so departed records free their slots for
        # replacement clients in this same update.
        snapshot_complete = complete_snapshot and len(clients_to_process) == len(clients)
        removed_count = 0
        if snapshot_complete:
            current_client_ids = {client.id for client in clients_to_process}
            departed_client_ids = network_clients.keys() - current_client_ids
            removed_count = len(departed_client_ids)
            for client_id in departed_client_ids:
                del network_clients[client_id]

        # Global cap (#533): computed once up-front so it is stable across the
        # whole call even though new clients are added to the store as we go.
        global_total = (
            sum(len(clients_in_network) for clients_in_network in self._clients.values())
            - len(published_network_clients)
            + len(network_clients)
        )
        global_capacity = max(self.max_clients_total - global_total, 0)

        # Process each client
        for client in clients_to_process:
            client_id = client.id

            # Get hostname from resolved list
            hostname = None
            if hostnames and client.ip:
                hostname = hostnames.get(client.ip)

            # Calculate the hostname that will be used in metrics
            # This follows the same logic as ClientsCollector._determine_hostname
            calculated_hostname = hostname or client.description or client.ip or "unknown"
            api_owned_values = {
                field_name: getattr(client, field_name) for field_name in _API_OWNED_CLIENT_FIELDS
            }

            # Create or update client data
            if client_id in network_clients:
                # Preserve DNS-derived state, but replace every value owned by
                # getNetworkClients so display and identity data cannot go stale.
                existing = network_clients[client_id]
                network_clients[client_id] = existing.model_copy(
                    update={
                        **api_owned_values,
                        "hostname": hostname or existing.hostname,
                        "calculatedHostname": calculated_hostname,
                        "networkId": network_id,
                        "networkName": (
                            network_name if network_name is not None else existing.networkName
                        ),
                        "organizationId": (
                            org_id if org_id is not None else existing.organizationId
                        ),
                    }
                )
                updated_count += 1
            else:
                # Global cap reached: skip creating new clients, but existing
                # clients (handled in the branch above) always continue to be
                # updated.
                if new_count >= global_capacity:
                    skipped_new_count += 1
                    continue

                # Add new client
                network_clients[client_id] = ClientData(
                    **api_owned_values,
                    hostname=hostname,
                    calculatedHostname=calculated_hostname,
                    networkId=network_id,
                    networkName=network_name,
                    organizationId=org_id,
                )
                new_count += 1

        if skipped_new_count > 0:
            logger.warning(
                "Global client store cap reached; not adding new clients",
                network_id=network_id,
                skipped=skipped_new_count,
                global_cap=self.max_clients_total,
            )

        # Publish the complete replacement and timestamp atomically.
        self._clients[network_id] = network_clients
        self._last_update[network_id] = time.time()

        # F-171: per-network line demoted to debug to avoid ~2,400 INFO lines/hour
        # at ~100 networks; the aggregate collection summary is emitted at INFO by
        # ClientsCollector instead.
        logger.debug(
            "Updated client data",
            network_id=network_id,
            network_name=network_name,
            new_clients=new_count,
            updated_clients=updated_count,
            removed_clients=removed_count,
            total_clients=len(network_clients),
        )

    def get_client(self, network_id: str, client_id: str) -> ClientData | None:
        """Get a specific client.

        Parameters
        ----------
        network_id : str
            Network ID.
        client_id : str
            Client ID.

        Returns
        -------
        ClientData | None
            Client data or None if not found.

        """
        if network_id not in self._clients:
            return None

        return self._clients[network_id].get(client_id)

    def get_network_clients(self, network_id: str) -> list[ClientData]:
        """Get all clients for a network.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[ClientData]
            List of clients for the network.

        """
        if network_id not in self._clients:
            return []

        return list(self._clients[network_id].values())

    def get_all_clients(self) -> list[ClientData]:
        """Get all clients across all networks.

        Returns
        -------
        list[ClientData]
            List of all clients.

        """
        clients: list[ClientData] = []
        for network_clients in self._clients.values():
            clients.extend(network_clients.values())
        return clients

    def get_page_snapshot(self, *, page: int, page_size: int) -> ClientPageSnapshot:
        """Return one bounded client page with aggregate store statistics.

        The full cache traversal needed for the aggregate values deliberately
        stays here so callers can offload the entire operation. Client records
        are selected from the insertion-ordered network and client maps without
        materializing the rest of the cache.

        Parameters
        ----------
        page : int
            One-based requested page number.
        page_size : int
            Maximum number of client records to include.

        Returns
        -------
        ClientPageSnapshot
            The selected client records and page navigation metadata.

        """
        with self._lock:
            published_networks = tuple(self._clients.values())
            network_count = len(published_networks)
        return self._get_page_snapshot(
            published_networks,
            network_count=network_count,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def _get_page_snapshot(
        published_networks: tuple[dict[str, ClientData], ...],
        *,
        network_count: int,
        page: int,
        page_size: int,
    ) -> ClientPageSnapshot:
        """Build a page from immutable published client-map references."""
        total_clients = 0
        online_clients = 0
        for network_clients in published_networks:
            total_clients += len(network_clients)
            online_clients += sum(client.status == "Online" for client in network_clients.values())

        total_pages = max((total_clients + page_size - 1) // page_size, 1)
        current_page = min(page, total_pages)
        offset = (current_page - 1) * page_size
        clients: list[ClientData] = []
        skipped = 0

        for network_clients in published_networks:
            for client in network_clients.values():
                if skipped < offset:
                    skipped += 1
                    continue
                clients.append(client)
                if len(clients) == page_size:
                    return ClientPageSnapshot(
                        clients=clients,
                        total_clients=total_clients,
                        online_clients=online_clients,
                        network_count=network_count,
                        page=current_page,
                        total_pages=total_pages,
                    )

        return ClientPageSnapshot(
            clients=clients,
            total_clients=total_clients,
            online_clients=online_clients,
            network_count=network_count,
            page=current_page,
            total_pages=total_pages,
        )

    def get_client_by_mac(self, mac: str) -> ClientData | None:
        """Find a client by MAC address.

        Parameters
        ----------
        mac : str
            MAC address to search for.

        Returns
        -------
        ClientData | None
            Client data or None if not found.

        """
        mac_lower = mac.lower()
        for network_clients in self._clients.values():
            for client in network_clients.values():
                if client.mac.lower() == mac_lower:
                    return client
        return None

    def get_clients_by_ip(self, ip: str) -> list[ClientData]:
        """Find clients by IP address.

        Parameters
        ----------
        ip : str
            IP address to search for.

        Returns
        -------
        list[ClientData]
            List of clients with this IP.

        """
        clients: list[ClientData] = []
        for network_clients in self._clients.values():
            for client in network_clients.values():
                if client.ip == ip:
                    clients.append(client)
        return clients

    def is_network_stale(self, network_id: str) -> bool:
        """Check if network data is stale.

        Parameters
        ----------
        network_id : str
            Network ID to check.

        Returns
        -------
        bool
            True if data is stale or missing.

        """
        if network_id not in self._last_update:
            return True

        age = time.time() - self._last_update[network_id]
        return age > self.cache_ttl

    def get_network_names(self) -> dict[str, str]:
        """Get all known network names.

        Returns
        -------
        dict[str, str]
            Mapping of network ID to name.

        """
        return self._network_names.copy()

    def get_statistics(self) -> dict[str, Any]:
        """Get store statistics.

        Returns
        -------
        dict[str, Any]
            Store statistics.

        """
        total_clients = sum(len(clients) for clients in self._clients.values())
        online_clients = sum(
            1
            for clients in self._clients.values()
            for client in clients.values()
            if client.status == "Online"
        )

        return {
            "total_networks": len(self._clients),
            "total_clients": total_clients,
            "online_clients": online_clients,
            "offline_clients": total_clients - online_clients,
            "networks": {
                network_id: {
                    "name": self._network_names.get(network_id, "Unknown"),
                    "client_count": len(clients),
                    "last_update": datetime.fromtimestamp(
                        self._last_update.get(network_id, 0)
                    ).isoformat(),
                    "is_stale": self.is_network_stale(network_id),
                }
                for network_id, clients in self._clients.items()
            },
        }

    def clear(self) -> None:
        """Clear all stored data."""
        with self._lock:
            self._clients.clear()
            self._last_update.clear()
            self._network_names.clear()
            self._network_orgs.clear()
        logger.info("Client store cleared")

    def _evict_network(self, network_id: str) -> str | None:
        """Remove every record associated with one network as one operation."""
        with self._lock:
            network_name = self._network_names.get(network_id)
            self._clients.pop(network_id, None)
            self._last_update.pop(network_id, None)
            self._network_names.pop(network_id, None)
            self._network_orgs.pop(network_id, None)
            return network_name

    def cleanup_stale_networks(self) -> int:
        """Remove data for stale networks.

        Returns
        -------
        int
            Number of networks cleaned up.

        """
        with self._lock:
            stale_networks = [
                network_id for network_id in self._clients if self.is_network_stale(network_id)
            ]

            for network_id in stale_networks:
                network_name = self._evict_network(network_id)
                logger.info(
                    "Removed stale network data",
                    network_id=network_id,
                    network_name=network_name,
                )

        return len(stale_networks)
