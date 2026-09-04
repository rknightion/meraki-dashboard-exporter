"""Operation-aware sanitizer for an authorised, untracked capture set.

It deliberately does not open files: capture and review remain an explicit human step.
"""
# ruff: noqa: D102

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qsl, quote, unquote, urlencode

from .corpus import REQUIRED_OPERATIONS

MAC_PATTERN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f])")
IP_CANDIDATE = re.compile(r"(?<![0-9A-Fa-f:.])(?:[0-9A-Fa-f:.]+)(?![0-9A-Fa-f:.])")
AUTH_KEYS = {"authorization", "apikey", "xciscomerakiapikey", "token", "password", "secret"}
KEY_CATEGORIES = {
    "organizationid": "org",
    "organizationids": "org",
    "networkid": "network",
    "networkids": "network",
    "deviceid": "device",
    "deviceids": "device",
    "deviceserial": "device",
    "serial": "device",
    "serials": "device",
    "clientid": "client",
    "clientids": "client",
    "mac": "mac",
}
SENSITIVE_VALUE_KEYS = {
    "address",
    "lat",
    "lng",
    "latitude",
    "longitude",
    "notes",
    "tags",
    "url",
    "email",
    "phone",
    "configtemplateid",
    "configurationtemplateid",
    "enrollmentid",
    "enrollmentstring",
    "user",
    "username",
}
SAFE_VALUE_KEYS = {
    "status",
    "model",
    "producttype",
    "producttypes",
    "firmware",
    "version",
    "type",
    "state",
    "enabled",
}
CAPTURE_FIELDS = {
    "operation",
    "captured_at_utc",
    "method",
    "path",
    "query",
    "status_code",
    "payload",
}
PATH_IDENTIFIER_CATEGORIES = {
    "organizations": "org",
    "networks": "network",
    "devices": "device",
}
PUBLIC_QUERY_KEYS = {
    "autoresolution",
    "fields",
    "interval",
    "perpage",
    "producttypes",
    "quantity",
    "resolution",
    "timespan",
}
SENSITIVE_CONTEXT_FIELDS = {("cdp", "version")}


class SanitizationError(ValueError):
    """A capture contains credentials and must not become corpus material."""


@dataclass
class PlaceholderState:
    """Shared capture-set identity mapping, preserving cross-file references."""

    reserved_strings: set[str] = field(default_factory=set)
    reserved_numbers: set[int | float] = field(default_factory=set)
    values: dict[tuple[str, str], str] = field(default_factory=dict)
    numeric_values: dict[tuple[str, int | float], int] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    def value(self, category: str, raw: str) -> str:
        key = (category, raw)
        if key not in self.values:
            while True:
                number = self.counters.get(category, 0) + 1
                self.counters[category] = number
                if category == "mac":
                    candidate = f"02:00:00:00:00:{number:02x}"
                elif category == "ipv4":
                    candidate = f"192.0.2.{number}"
                elif category == "ipv6":
                    candidate = f"2001:db8::{number}"
                else:
                    candidate = f"{category}_{number:03d}"
                if candidate not in self.reserved_strings:
                    self.values[key] = candidate
                    break
        return self.values[key]

    def numeric_value(self, category: str, raw: int | float) -> int:
        """Return a stable integer placeholder while preserving identifier type."""
        key = (category, raw)
        if key not in self.numeric_values:
            while True:
                number = self.counters.get(category, 0) + 1
                self.counters[category] = number
                candidate = 900_000_000_000_000_000 + number
                if candidate not in self.reserved_numbers:
                    self.numeric_values[key] = candidate
                    break
        return self.numeric_values[key]


def sanitize_capture_set(captures: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Sanitize and de-duplicate route captures with one shared placeholder state."""
    ordered: list[tuple[datetime, int, Mapping[str, object]]] = []
    for index, capture in enumerate(captures):
        extra = sorted(set(capture) - CAPTURE_FIELDS)
        missing_fields = sorted(CAPTURE_FIELDS - set(capture))
        if extra or missing_fields:
            detail = ", ".join(
                part
                for part in (
                    f"missing {', '.join(missing_fields)}" if missing_fields else "",
                    f"unexpected {', '.join(extra)}" if extra else "",
                )
                if part
            )
            raise SanitizationError(f"capture row {index} has invalid fields ({detail})")
        operation = capture["operation"]
        captured_at_raw = capture["captured_at_utc"]
        method = capture["method"]
        path = capture["path"]
        query = capture["query"]
        status_code = capture["status_code"]
        if not isinstance(operation, str):
            raise SanitizationError(f"capture row {index} has invalid string metadata")
        if not isinstance(captured_at_raw, str):
            raise SanitizationError(f"capture row {index} has invalid string metadata")
        if not isinstance(method, str):
            raise SanitizationError(f"capture row {index} has invalid string metadata")
        if not isinstance(path, str):
            raise SanitizationError(f"capture row {index} has invalid string metadata")
        if not isinstance(query, str):
            raise SanitizationError(f"capture row {index} has invalid string metadata")
        if method != "GET" or not path.startswith("/"):
            raise SanitizationError(f"capture row {index} is not an absolute read-only GET route")
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 100 <= status_code < 600
        ):
            raise SanitizationError(f"capture row {index} has invalid status_code")
        try:
            captured_at = datetime.fromisoformat(captured_at_raw)
        except ValueError as error:
            raise SanitizationError(f"capture row {index} has invalid captured_at_utc") from error
        if captured_at.tzinfo is None:
            raise SanitizationError(f"capture row {index} captured_at_utc is not timezone-aware")
        ordered.append((captured_at, index, capture))

    unique: list[Mapping[str, object]] = []
    seen_routes: set[tuple[str, str, str]] = set()
    for _, _, capture in sorted(ordered):
        route = (str(capture["method"]), str(capture["path"]), str(capture["query"]))
        if route in seen_routes:
            continue
        seen_routes.add(route)
        unique.append(capture)
    unique = _coalesce_paginated_routes(unique)

    reserved_strings: set[str] = set()
    reserved_numbers: set[int | float] = set()
    _collect_scalar_values(unique, reserved_strings, reserved_numbers)
    state = PlaceholderState(
        reserved_strings=reserved_strings,
        reserved_numbers=reserved_numbers,
    )
    sanitized_payloads = [
        _sanitize(
            capture["payload"],
            str(capture["operation"]),
            state,
            None,
            None,
        )
        for capture in unique
    ]
    sanitized: list[dict[str, object]] = []
    for capture, payload in zip(unique, sanitized_payloads, strict=True):
        operation = str(capture["operation"])
        row: dict[str, object] = {
            "operation": operation,
            "captured_at_utc": capture["captured_at_utc"],
            "method": capture["method"],
            "path": _sanitize_path(str(capture["path"]), state),
            "query": _sanitize_query(str(capture["query"]), operation, state),
            "status_code": capture["status_code"],
            "payload": payload,
        }
        for provenance_field in ("source_route_count", "captured_through_utc"):
            if provenance_field in capture:
                row[provenance_field] = capture[provenance_field]
        sanitized.append(row)
    operations = {str(capture["operation"]) for capture in unique}
    missing = sorted(REQUIRED_OPERATIONS - operations)
    if missing:
        raise SanitizationError(f"capture set missing required operations: {', '.join(missing)}")
    return sanitized


def _collect_scalar_values(
    value: object,
    strings: set[str],
    numbers: set[int | float],
) -> None:
    """Reserve every captured scalar so no generated placeholder can reproduce it."""
    if isinstance(value, Mapping):
        for nested in value.values():
            _collect_scalar_values(nested, strings, numbers)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for nested in value:
            _collect_scalar_values(nested, strings, numbers)
    elif isinstance(value, str):
        strings.add(value)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        numbers.add(value)


def _coalesce_paginated_routes(
    captures: list[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    """Coalesce captured cursor pages into the initial route's replay body."""
    result: list[Mapping[str, object]] = []
    consumed: set[int] = set()
    for index, capture in enumerate(captures):
        if index in consumed:
            continue
        base, has_cursor = _pagination_identity(str(capture["query"]))
        if has_cursor or not isinstance(capture["payload"], list):
            result.append(capture)
            continue
        pages = [index]
        for candidate_index in range(index + 1, len(captures)):
            candidate = captures[candidate_index]
            candidate_base, candidate_has_cursor = _pagination_identity(str(candidate["query"]))
            same_route_family = tuple(
                candidate[field] for field in ("operation", "method", "path", "status_code")
            ) == tuple(capture[field] for field in ("operation", "method", "path", "status_code"))
            if (
                candidate_has_cursor
                and candidate_base == base
                and same_route_family
                and isinstance(candidate["payload"], list)
            ):
                pages.append(candidate_index)
        if len(pages) == 1:
            result.append(capture)
            continue
        merged = dict(capture)
        merged_payload: list[object] = []
        for page_index in pages:
            payload = captures[page_index]["payload"]
            if not isinstance(payload, list):
                raise SanitizationError("pagination payload changed after validation")
            merged_payload.extend(payload)
        merged["payload"] = merged_payload
        merged["source_route_count"] = len(pages)
        merged["captured_through_utc"] = captures[pages[-1]]["captured_at_utc"]
        consumed.update(pages[1:])
        result.append(merged)
    return result


def _pagination_identity(query: str) -> tuple[tuple[tuple[str, str], ...], bool]:
    pairs = parse_qsl(query, keep_blank_values=True)
    cursor_keys = {"endingBefore", "startingAfter"}
    return tuple(sorted((key, value) for key, value in pairs if key not in cursor_keys)), any(
        key in cursor_keys for key, _ in pairs
    )


def _sanitize_path(path: str, state: PlaceholderState) -> str:
    """Replace identifiers in known Meraki path parameter positions."""
    parts = path.split("/")
    known_identifiers = {
        raw
        for (category, raw) in state.values
        if category in {"org", "network", "device", "client", "mac", "ipv4", "ipv6"}
        or category.endswith("_id")
    }
    for index in range(1, len(parts)):
        category = PATH_IDENTIFIER_CATEGORIES.get(parts[index - 1])
        raw = unquote(parts[index])
        if category and (category, raw) in state.values:
            parts[index] = quote(state.value(category, raw), safe="-._~")
        elif raw in known_identifiers:
            raise SanitizationError(
                f"unmapped identifier path segment follows {parts[index - 1]!r}"
            )
    return "/".join(parts)


def _sanitize_query(query: str, operation: str, state: PlaceholderState) -> str:
    """Sanitize query values while preserving key order and repeated parameters."""
    pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        if not value or normalized in PUBLIC_QUERY_KEYS:
            sanitized = value
        elif normalized == "clients":
            sanitized = ",".join(state.value("client", item) for item in value.split(","))
        else:
            sanitized = str(_sanitize(value, operation, state, key, None))
        pairs.append((key, sanitized))
    return urlencode(pairs)


def _sanitize(
    value: object,
    operation: str,
    state: PlaceholderState,
    key: str | None,
    parent_key: str | None,
) -> object:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower()) if key else ""
    normalized_parent = re.sub(r"[^a-z0-9]", "", parent_key.lower()) if parent_key else ""
    if normalized in AUTH_KEYS:
        raise SanitizationError("credential or authorization field is forbidden")
    if isinstance(value, Mapping):
        return {str(k): _sanitize(v, operation, state, str(k), key) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, operation, state, key, parent_key) for item in value]
    if normalized in SENSITIVE_VALUE_KEYS and not isinstance(value, str):
        if normalized in {"lat", "lng", "latitude", "longitude"}:
            return 0.0
        return None
    if not isinstance(value, str):
        if isinstance(value, int | float) and normalized.endswith(("id", "ids")):
            return state.numeric_value(_identifier_category(normalized, normalized_parent), value)
        return value
    category = KEY_CATEGORIES.get(normalized)
    if normalized == "id":
        category = (
            normalized_parent
            if normalized_parent in {"org", "organization", "network", "device"}
            else _operation_category(operation)
        )
        if category == "organization":
            category = "org"
    elif category is None and normalized.endswith(("id", "ids")):
        category = _identifier_category(normalized, normalized_parent)
    if normalized in {"name", "organizationname", "networkname", "devicename"}:
        category = f"{_operation_category(operation)}_name"
    if category:
        return state.value(category, value)
    if normalized in SENSITIVE_VALUE_KEYS:
        return state.value(f"{normalized}_value", value)
    if (normalized_parent, normalized) in SENSITIVE_CONTEXT_FIELDS:
        return state.value(f"{normalized_parent}_{normalized}_value", value)
    if normalized in {"ip", "ipaddress", "ipv4", "ipv6", "gateway", "publicip"}:
        return _replace_network_identifiers(value, state)
    if _is_timestamp(value):
        return "2026-01-01" if len(value) == 10 else "2026-01-01T00:00:00Z"
    if normalized not in SAFE_VALUE_KEYS:
        # Capture values are user-controlled unless a schema field is clearly an enum/product value.
        return state.value("value", value)
    return _replace_network_identifiers(value, state)


def _is_timestamp(value: str) -> bool:
    """Recognize ISO dates/timestamps so sanitized payloads remain schema-valid."""
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-"


def _operation_category(operation: str) -> str:
    lowered = operation.lower()
    if "client" in lowered:
        return "client"
    if "network" in lowered:
        return "network"
    if "device" in lowered:
        return "device"
    return "org"


def _identifier_category(normalized: str, parent: str) -> str:
    """Derive a stable placeholder namespace from an identifier field path."""
    if normalized == "id" and parent in {"org", "organization", "network", "device"}:
        return "org" if parent == "organization" else parent
    stem = normalized.removesuffix("ids").removesuffix("id")
    return f"{stem or 'identifier'}_id"


def _replace_network_identifiers(value: str, state: PlaceholderState) -> str:
    value = MAC_PATTERN.sub(lambda match: state.value("mac", match.group(0).lower()), value)

    def replace_ip(match: re.Match[str]) -> str:
        candidate = match.group(0)
        try:
            parsed = ipaddress.ip_address(candidate)
        except ValueError:
            return candidate
        category = "ipv4" if parsed.version == 4 else "ipv6"
        return state.value(category, candidate)

    return IP_CANDIDATE.sub(replace_ip, value)
