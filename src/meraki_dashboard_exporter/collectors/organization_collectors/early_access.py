"""Organization Early Access opt-in collector (#278, #279).

Surfaces an organization's Meraki Early Access feature opt-ins as operational
signals:

- ``meraki_org_early_access_opt_in_info`` — an ``*_info``-style join carrier
  (value 1), one series per active opt-in, labelled by the opt-in's ``feature``
  (``shortName``) and ``opt_in_id``. Per the #534 contract the mutable string
  values live only on this info carrier.
- ``meraki_org_early_access_opt_in_scoped_networks`` — a small gauge holding the
  *count* of networks each opt-in is scoped to (0 = org-wide), labelled by
  ``feature`` only. The scope network IDs are deliberately NOT expanded into
  per-network series (that would fan out unbounded).
- ``meraki_org_has_beta_api`` — a dedicated 0/1 risk gauge, emitted for EVERY
  org (0 when absent) so absence is queryable rather than a missing series, plus
  an operational WARN log when the org is on the beta API spec.

Always-on: there is no config gate. This intentionally builds NONE of the
de-scoped beta *consumer* machinery (#280/#282, closed) — no ``BetaAPISettings``,
no ``has_beta_api`` detection cache, no raw beta-spec ``_session`` calls. It only
reports opt-in state.

``getOrganizationEarlyAccessFeaturesOptIns`` is a pure GET
(``dashboard:iam:config:read``). Opt-ins are toggled by an admin and change on
the order of days/weeks, so this is SLOW-volatility data; it is nonetheless a
single cheap org-scoped call, so it runs once per organization cycle without its
own scheduler endpoint group (a dedicated budget group could be added later).
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_org_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from .base import BaseOrganizationCollector

logger = get_logger(__name__)

# Opt-in shortName that signals the org is opted into the Meraki beta API spec.
_BETA_API_SHORTNAME = "has_beta_api"


class EarlyAccessOptIn(BaseModel):
    """Lenient model of a single Early Access opt-in object.

    The exact shape may vary across API versions, so every field is optional and
    unknown keys are ignored; a row that still fails validation is skipped by the
    collector rather than failing the whole run.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = None
    short_name: str | None = Field(default=None, alias="shortName")
    long_name: str | None = Field(default=None, alias="longName")
    created_at: str | None = Field(default=None, alias="createdAt")
    # Networks this opt-in is scope-limited to; only its COUNT is emitted.
    limit_scope_to_networks: list[Any] = Field(default_factory=list, alias="limitScopeToNetworks")


class EarlyAccessCollector(BaseOrganizationCollector):
    """Collector for organization Early Access opt-in state (#278, #279)."""

    @log_api_call("getOrganizationEarlyAccessFeaturesOptIns")
    async def _fetch_opt_ins(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch the organization's Early Access feature opt-ins."""
        self._track_api_call("getOrganizationEarlyAccessFeaturesOptIns")
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationEarlyAccessFeaturesOptIns,
            org_id,
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationEarlyAccessFeaturesOptIns",
            ),
        )

    @with_error_handling(
        operation="Collect early access opt-in metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str) -> bool:
        """Collect Early Access opt-in inventory + beta-API risk metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        Returns
        -------
        bool
            ``True`` on success or when the endpoint is unavailable for this org
            (404); on a real (non-404) failure the error is re-raised so the
            decorator can retry rate limits and then swallow it. The coordinator
            treats any non-``True`` result as a failure (F-172).

        """
        try:
            with LogContext(org_id=org_id, org_name=org_name):
                raw = await self._fetch_opt_ins(org_id)
        except Exception as e:
            if "404" in str(e):
                logger.debug(
                    "Early access opt-ins endpoint not available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
                return True
            raise  # Let decorator handle non-404 errors (retry + swallow)

        self._process_opt_ins(org_id, org_name, raw)
        return True

    def _process_opt_ins(self, org_id: str, org_name: str, raw: list[dict[str, Any]]) -> None:
        """Emit opt-in inventory + scoped-network + has_beta_api metrics.

        Malformed rows are skipped (debug-logged) rather than failing the run.
        ``createdAt`` is deliberately NOT emitted as a label: it adds no query
        value and would need its own label member; the opt-in inventory is fully
        described by ``feature`` + ``opt_in_id``.
        """
        org_data = {"id": org_id, "name": org_name}
        has_beta_api = False
        emitted = 0

        for row in raw:
            if not isinstance(row, dict):
                logger.debug(
                    "Skipping malformed early access opt-in row (not an object)",
                    org_id=org_id,
                )
                continue
            try:
                opt_in = EarlyAccessOptIn.model_validate(row)
            except ValidationError as e:
                logger.debug(
                    "Skipping malformed early access opt-in row",
                    org_id=org_id,
                    error=str(e),
                )
                continue

            short_name = opt_in.short_name
            if not short_name:
                logger.debug(
                    "Skipping early access opt-in with no shortName",
                    org_id=org_id,
                )
                continue

            emitted += 1
            opt_in_id = opt_in.id or ""

            # Info-style inventory series (value 1); mutable feature/id strings
            # live only on this carrier (#534).
            info_labels = create_org_labels(org_data, feature=short_name, opt_in_id=opt_in_id)
            self._set_metric_value("_org_early_access_opt_in_info", info_labels, 1)

            # Scoped-network COUNT (0 = org-wide), by feature — never one series
            # per scoped network.
            scoped_count = len(opt_in.limit_scope_to_networks)
            count_labels = create_org_labels(org_data, feature=short_name)
            self._set_metric_value(
                "_org_early_access_opt_in_scoped_networks", count_labels, scoped_count
            )

            if short_name == _BETA_API_SHORTNAME:
                has_beta_api = True

        # Emit for EVERY org (0 when absent) so absence is queryable, not missing.
        beta_labels = create_org_labels(org_data)
        self._set_metric_value("_org_has_beta_api", beta_labels, 1 if has_beta_api else 0)

        # Operational risk signal — once per org per cycle, not per opt-in.
        if has_beta_api:
            logger.warning(
                "Organization has opted into the Meraki beta API spec (has_beta_api); "
                "endpoints this exporter assumes are stable may now be served from the "
                "beta spec and could change shape or break - investigate",
                org_id=org_id,
                org_name=org_name,
            )

        logger.debug(
            "Collected early access opt-in metrics",
            org_id=org_id,
            org_name=org_name,
            opt_ins=emitted,
            has_beta_api=has_beta_api,
        )
