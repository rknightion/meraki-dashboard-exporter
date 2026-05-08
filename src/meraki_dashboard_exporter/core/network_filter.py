"""Pure network-filter logic.

Given a :class:`NetworkFilterSettings` and a list of network dicts, decide
which networks should be scraped. Pure: no I/O, no caching of network
lists. Callers (typically :class:`OrganizationInventory`) are responsible
for memoising the resolved set when desired.
"""

from __future__ import annotations

import fnmatch
from typing import Any

import structlog

from .config_models import NetworkFilterSettings

logger = structlog.get_logger(__name__)


class NetworkFilter:
    """Apply include/exclude rules across name (glob), id, and tag.

    Resolution semantics
    --------------------
    1. If any include rule (across name OR id OR tag) is configured, a
       network must match at least one include rule to be considered.
       Matching is logical OR across dimensions.
    2. If a network matches any exclude rule (across name OR id OR tag),
       it is dropped. Excludes beat includes when both apply.
    3. If no rules are configured at all (``is_active`` is False), every
       network is passed through unchanged.

    Examples
    --------
    >>> from .config_models import NetworkFilterSettings
    >>> nf = NetworkFilter(NetworkFilterSettings(include_names=["prod-*"]))
    >>> nf.apply([{"id": "L_1", "name": "prod-a", "tags": []}])
    [{'id': 'L_1', 'name': 'prod-a', 'tags': []}]

    """

    def __init__(self, settings: NetworkFilterSettings) -> None:
        """Initialise with a :class:`NetworkFilterSettings` instance.

        Parameters
        ----------
        settings : NetworkFilterSettings
            The configured filter rules. May be inactive (no rules set).

        """
        self._settings = settings
        self._include_ids_set = set(settings.include_ids)
        self._include_tags_set = set(settings.include_tags)
        self._exclude_ids_set = set(settings.exclude_ids)
        self._exclude_tags_set = set(settings.exclude_tags)

    @property
    def is_active(self) -> bool:
        """Whether any include or exclude rule is configured."""
        return self._settings.is_active

    def matches(self, network: dict[str, Any]) -> bool:
        """Return True iff this single network passes the filter.

        Parameters
        ----------
        network : dict[str, Any]
            A network dict as returned by ``getOrganizationNetworks``.
            Expected keys: ``id``, ``name``, ``tags``. Missing keys are
            handled gracefully (treated as empty values).

        Returns
        -------
        bool
            True iff the network is included by the filter.

        """
        if not self.is_active:
            return True

        name = network.get("name", "")
        net_id = network.get("id", "")
        tags = set(network.get("tags") or [])

        any_include = (
            self._settings.include_names or self._include_ids_set or self._include_tags_set
        )
        if any_include:
            included = (
                any(fnmatch.fnmatchcase(name, pat) for pat in self._settings.include_names)
                or net_id in self._include_ids_set
                or bool(tags & self._include_tags_set)
            )
            if not included:
                return False

        if (
            any(fnmatch.fnmatchcase(name, pat) for pat in self._settings.exclude_names)
            or net_id in self._exclude_ids_set
            or bool(tags & self._exclude_tags_set)
        ):
            return False

        return True

    def apply(self, networks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return only the networks that pass the filter.

        Also emits warnings for any ``include_ids`` or ``include_tags`` that
        did not match anything in the input list, to help catch typos.

        Parameters
        ----------
        networks : list[dict[str, Any]]
            All candidate networks for an organisation.

        Returns
        -------
        list[dict[str, Any]]
            The subset that passed the filter. Returns a shallow copy when
            inactive so callers may safely mutate.

        """
        if not self.is_active:
            return list(networks)

        result = [n for n in networks if self.matches(n)]
        self._warn_unmatched(networks)
        return result

    def resolved_ids(self, networks: list[dict[str, Any]]) -> set[str]:
        """Return the set of network IDs that pass the filter.

        Parameters
        ----------
        networks : list[dict[str, Any]]
            All candidate networks for an organisation.

        Returns
        -------
        set[str]
            The set of ``id`` values for networks that passed the filter.

        """
        return {n["id"] for n in self.apply(networks) if "id" in n}

    def _warn_unmatched(self, networks: list[dict[str, Any]]) -> None:
        """Warn about ``include_ids``/``include_tags`` that matched nothing."""
        if not self._include_ids_set and not self._include_tags_set:
            return

        present_ids = {n.get("id") for n in networks}
        for missing in sorted(self._include_ids_set - present_ids):
            logger.warning(
                "Network filter include_id did not match any network",
                missing_id=missing,
            )

        present_tags: set[str] = set()
        for n in networks:
            present_tags.update(n.get("tags") or [])
        for missing in sorted(self._include_tags_set - present_tags):
            logger.warning(
                "Network filter include_tag did not match any network",
                missing_tag=missing,
            )
