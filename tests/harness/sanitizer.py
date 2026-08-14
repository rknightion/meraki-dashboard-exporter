"""Operation-aware sanitizer for an authorised, untracked capture set.

It deliberately does not open files: capture and review remain an explicit human step.
"""
# ruff: noqa: D102

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from .corpus import REQUIRED_OPERATIONS

MAC_PATTERN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f])")
IP_CANDIDATE = re.compile(r"(?<![0-9A-Fa-f:.])(?:[0-9A-Fa-f:.]+)(?![0-9A-Fa-f:.])")
AUTH_KEYS = {"authorization", "apikey", "xciscomerakiapikey", "token", "password", "secret"}
KEY_CATEGORIES = {
    "organizationid": "org",
    "networkid": "network",
    "serial": "device",
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


class SanitizationError(ValueError):
    """A capture contains credentials and must not become corpus material."""


@dataclass
class PlaceholderState:
    """Shared capture-set identity mapping, preserving cross-file references."""

    values: dict[tuple[str, str], str] = field(default_factory=dict)
    numeric_values: dict[tuple[str, int | float], int] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    def value(self, category: str, raw: str) -> str:
        key = (category, raw)
        if key not in self.values:
            number = self.counters.get(category, 0) + 1
            self.counters[category] = number
            if category == "mac":
                self.values[key] = f"02:00:00:00:00:{number:02x}"
            elif category == "ipv4":
                self.values[key] = f"192.0.2.{number}"
            elif category == "ipv6":
                self.values[key] = f"2001:db8::{number}"
            else:
                self.values[key] = f"{category}_{number:03d}"
        return self.values[key]

    def numeric_value(self, category: str, raw: int | float) -> int:
        """Return a stable integer placeholder while preserving identifier type."""
        key = (category, raw)
        if key not in self.numeric_values:
            number = self.counters.get(category, 0) + 1
            self.counters[category] = number
            self.numeric_values[key] = 900_000_000_000_000_000 + number
        return self.numeric_values[key]


def sanitize_capture_set(captures: Mapping[str, object]) -> dict[str, object]:
    """Sanitize a four-operation capture set using one stable placeholder state."""
    state = PlaceholderState()
    sanitized = {
        operation: _sanitize(payload, operation, state, None, None)
        for operation, payload in captures.items()
    }
    missing = sorted(REQUIRED_OPERATIONS - set(captures))
    if missing:
        raise SanitizationError(f"capture set missing required operations: {', '.join(missing)}")
    return sanitized


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
    if normalized in {"ip", "ipaddress", "ipv4", "ipv6", "gateway", "publicip"}:
        return _replace_network_identifiers(value, state)
    if normalized not in SAFE_VALUE_KEYS:
        # Capture values are user-controlled unless a schema field is clearly an enum/product value.
        return state.value("value", value)
    return _replace_network_identifiers(value, state)


def _operation_category(operation: str) -> str:
    lowered = operation.lower()
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
