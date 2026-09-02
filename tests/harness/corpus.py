"""Digest-pinned, provenance-bearing corpus loading for the failure harness."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final
from urllib.parse import parse_qsl, urlencode

LIVE_VERIFIED: Final = "LIVE-VERIFIED"
SHAPE_ASSUMED: Final = "SHAPE-ASSUMED"
REQUIRED_OPERATIONS: Final = frozenset({
    "getDeviceSwitchPortsStatuses",
    "getDeviceSwitchPortsStatusesPackets",
    "getNetworkBluetoothClients",
    "getNetworkClients",
    "getNetworkClientsApplicationUsage",
    "getNetworkSensorAlertsCurrentOverviewByMetric",
    "getNetworkSensorAlertsOverviewByMetric",
    "getNetworkSensorAlertsProfiles",
    "getNetworkSensorRelationships",
    "getNetworkSwitchDhcpServerPolicyArpInspectionWarningsByDevice",
    "getNetworkSwitchDhcpV4ServersSeen",
    "getNetworkSwitchLinkAggregations",
    "getNetworkSwitchStacks",
    "getNetworkSwitchStp",
    "getNetworkWirelessAirMarshal",
    "getNetworkWirelessClientsLatencyStats",
    "getNetworkWirelessConnectionStats",
    "getNetworkWirelessDataRateHistory",
    "getNetworkWirelessDevicesConnectionStats",
    "getNetworkWirelessDevicesLatencyStats",
    "getNetworkWirelessFailedConnections",
    "getNetworkWirelessMeshStatuses",
    "getNetworkWirelessSignalQualityHistory",
    "getNetworkWirelessSsids",
    "getOrganization",
    "getOrganizationAdaptivePolicyOverview",
    "getOrganizationAdmins",
    "getOrganizationApiRequests",
    "getOrganizationApiRequestsOverview",
    "getOrganizationAssuranceAlerts",
    "getOrganizationClientsOverview",
    "getOrganizationConfigTemplates",
    "getOrganizationConfigurationChanges",
    "getOrganizationNetworks",
    "getOrganizationDevices",
    "getOrganizationDevicesAvailabilities",
    "getOrganizationDevicesAvailabilitiesChangeHistory",
    "getOrganizationDevicesOverviewByModel",
    "getOrganizationDevicesPacketCaptureCaptures",
    "getOrganizationDevicesPowerModulesStatusesByDevice",
    "getOrganizationDevicesSystemMemoryUsageHistoryByInterval",
    "getOrganizationEarlyAccessFeaturesOptIns",
    "getOrganizationFirmwareUpgrades",
    "getOrganizationFirmwareUpgradesByDevice",
    "getOrganizationLicensesOverview",
    "getOrganizationLoginSecurity",
    "getOrganizationSaml",
    "getOrganizationSensorGatewaysConnectionsLatest",
    "getOrganizationSensorReadingsLatest",
    "getOrganizationSummarySwitchPowerHistory",
    "getOrganizationSummaryTopApplicationsCategoriesByUsage",
    "getOrganizationSummaryTopClientsByUsage",
    "getOrganizationSummaryTopClientsManufacturersByUsage",
    "getOrganizationSummaryTopSsidsByUsage",
    "getOrganizationSwitchPortsOverview",
    "getOrganizationSwitchPortsStatusesBySwitch",
    "getOrganizationWebhooksLogs",
    "getOrganizationWirelessClientsOverviewByDevice",
    "getOrganizationWirelessDevicesChannelUtilizationByDevice",
    "getOrganizationWirelessDevicesChannelUtilizationByNetwork",
    "getOrganizationWirelessDevicesEthernetStatuses",
    "getOrganizationWirelessDevicesPacketLossByDevice",
    "getOrganizationWirelessDevicesPacketLossByNetwork",
    "getOrganizationWirelessDevicesPowerModeHistory",
    "getOrganizationWirelessDevicesSystemCpuLoadHistory",
    "getOrganizationWirelessDevicesWirelessControllersByDevice",
    "getOrganizationWirelessRfProfilesAssignmentsByDevice",
    "getOrganizationWirelessSsidsStatusesByDevice",
    "getOrganizations",
})


class CorpusError(ValueError):
    """Raised when a replay corpus is absent, unsafe, or unverifiable."""


def canonical_query(query: str) -> str:
    """Return the stable semantic identity of a query string."""
    return urlencode(sorted(parse_qsl(query, keep_blank_values=True)))


@dataclass(frozen=True)
class Fixture:
    """One immutable route and its verified response fixture."""

    file: Path
    method: str
    path: str
    query: str
    sdk_operation: str
    status_code: int
    captured_at_utc: str


@dataclass(frozen=True)
class Corpus:
    """Verified fixtures rooted at the manifest directory."""

    fixtures: tuple[Fixture, ...]


def load_manifest(manifest_path: Path, *, require_real: bool) -> Corpus:
    """Load a manifest only when every row has valid provenance and digest."""
    if not manifest_path.is_file():
        raise CorpusError(f"corpus manifest is absent: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CorpusError(f"invalid manifest JSON: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
        raise CorpusError("unsupported manifest schema_version")
    rows = manifest.get("fixtures")
    if not isinstance(rows, list) or not rows:
        raise CorpusError("manifest must contain at least one fixture")

    fixtures: list[Fixture] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CorpusError(f"fixture row {index} is not an object")
        _validate_row(row, index, require_real)
        fixture_name = row["fixture"]
        if not isinstance(fixture_name, str):  # guarded by _validate_row; narrows for mypy
            raise CorpusError(f"fixture row {index} fixture must be a string")
        fixture_path = manifest_path.parent / fixture_name
        if not fixture_path.is_file():
            raise CorpusError(f"fixture row {index} is absent: {fixture_name}")
        digest = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            raise CorpusError(f"fixture row {index} digest mismatch")
        fixtures.append(
            Fixture(
                file=fixture_path,
                method=row["method"],
                path=row["path"],
                query=canonical_query(row.get("query", "")),
                sdk_operation=row["sdk_operation"],
                status_code=row["status_code"],
                captured_at_utc=row["captured_at_utc"],
            )
        )
    if require_real:
        _validate_real_corpus_contract(fixtures)
    return Corpus(tuple(fixtures))


def _validate_real_corpus_contract(fixtures: list[Fixture]) -> None:
    """Require the complete enabled-profile operation set and unique HTTP routes."""
    operations = {fixture.sdk_operation for fixture in fixtures}
    if operations != REQUIRED_OPERATIONS:
        missing = sorted(REQUIRED_OPERATIONS - operations)
        unexpected = sorted(operations - REQUIRED_OPERATIONS)
        detail = ", ".join(
            part
            for part in (
                f"missing {', '.join(missing)}" if missing else "",
                f"unexpected {', '.join(unexpected)}" if unexpected else "",
            )
            if part
        )
        raise CorpusError(f"real corpus must contain exactly the required operations ({detail})")
    routes = [(fixture.method, fixture.path, fixture.query) for fixture in fixtures]
    if len(routes) != len(set(routes)):
        raise CorpusError("duplicate method/path/query route")


def _validate_row(row: dict[str, object], index: int, require_real: bool) -> None:
    required_strings = (
        "fixture",
        "sha256",
        "captured_at_utc",
        "product_family",
        "method",
        "path",
        "sdk_operation",
        "evidence_source",
        "evidence_status",
    )
    missing = [
        field for field in required_strings if not isinstance(row.get(field), str) or not row[field]
    ]
    if missing:
        raise CorpusError(f"fixture row {index} missing required fields: {', '.join(missing)}")
    sanitizer = row.get("sanitizer")
    if not isinstance(sanitizer, dict) or not all(
        isinstance(sanitizer.get(field), str) and sanitizer[field]
        for field in ("name", "version", "method")
    ):
        raise CorpusError(f"fixture row {index} has incomplete sanitizer provenance")
    status = row["evidence_status"]
    if status not in {LIVE_VERIFIED, SHAPE_ASSUMED}:
        raise CorpusError(f"fixture row {index} has invalid evidence status")
    if require_real and status != LIVE_VERIFIED:
        raise CorpusError(f"fixture row {index} must be {LIVE_VERIFIED}")
    if not str(row["path"]).startswith("/"):
        raise CorpusError(f"fixture row {index} path must start with /")
    if not str(row["method"]).isupper():
        raise CorpusError(f"fixture row {index} method must be uppercase")
    status_code = row.get("status_code")
    if (
        isinstance(status_code, bool)
        or not isinstance(status_code, int)
        or not 100 <= status_code < 600
    ):
        raise CorpusError(f"fixture row {index} has invalid status_code")
    try:
        captured_at = datetime.fromisoformat(str(row["captured_at_utc"]))
    except ValueError as error:
        raise CorpusError(f"fixture row {index} has invalid captured_at_utc") from error
    if captured_at.tzinfo is None:
        raise CorpusError(f"fixture row {index} captured_at_utc must be timezone-aware")
