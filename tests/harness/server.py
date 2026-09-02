"""Low-level HTTPS replay origin with deterministic, externally recorded faults."""
# ruff: noqa: D101, D102, D107

from __future__ import annotations

import asyncio
import json
import os
import ssl
import time
from dataclasses import asdict, dataclass
from email.utils import formatdate
from enum import StrEnum
from pathlib import Path
from typing import Final

from .corpus import Corpus, Fixture, canonical_query, load_manifest

STALL_HOLD_SECONDS: Final = 0.25


class FaultMode(StrEnum):
    BASELINE = "baseline"
    TRUSTED_TLS = "trusted_tls"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    RATE_LIMIT_SECONDS = "rate_limit_seconds"
    RATE_LIMIT_HTTP_DATE = "rate_limit_http_date"
    TIMEOUT = "timeout"
    STALL = "stall"
    TLS_FAILURE = "tls_failure"
    HTML = "html"
    SLOW_VALID = "slow_valid"
    RESET = "reset"
    DNS_FAILURE = "dns_failure"
    SERVER_ERROR = "server_error"


@dataclass(frozen=True)
class FaultDecision:
    reason: str
    evidence: str
    status: int | None = None
    retry_after: str | None = None
    transport_reset: bool = False
    origin_host: str = "replay-origin"


def fault_decision(mode: FaultMode) -> FaultDecision:
    """Map each selectable mode to a journal-verifiable transport decision."""
    decisions = {
        FaultMode.BASELINE: FaultDecision("fault:baseline", "matched verified fixture"),
        FaultMode.TRUSTED_TLS: FaultDecision("fault:trusted_tls", "trusted replay-origin SAN"),
        FaultMode.UNAUTHORIZED: FaultDecision("fault:unauthorized", "HTTP 401", 401),
        FaultMode.FORBIDDEN: FaultDecision("fault:forbidden", "HTTP 403", 403),
        FaultMode.RATE_LIMIT_SECONDS: FaultDecision(
            "fault:rate_limit_seconds", "HTTP 429 Retry-After seconds", 429, "2"
        ),
        FaultMode.RATE_LIMIT_HTTP_DATE: FaultDecision(
            "fault:rate_limit_http_date",
            "HTTP 429 Retry-After HTTP-date",
            429,
            formatdate(time.time() + 2, usegmt=True),
        ),
        FaultMode.TIMEOUT: FaultDecision(
            "fault:timeout", "origin holds request past exporter timeout"
        ),
        FaultMode.STALL: FaultDecision("fault:stall", "origin holds request until teardown"),
        FaultMode.TLS_FAILURE: FaultDecision("fault:tls_failure", "exporter trusts alternate CA"),
        FaultMode.HTML: FaultDecision("fault:html", "HTTP 200 HTML body", 200),
        FaultMode.SLOW_VALID: FaultDecision("fault:slow_valid", "delayed valid fixture"),
        FaultMode.RESET: FaultDecision(
            "fault:reset", "TCP connection aborted", transport_reset=True
        ),
        FaultMode.DNS_FAILURE: FaultDecision(
            "fault:dns_failure",
            "origin set to unresolvable.invalid",
            origin_host="unresolvable.invalid",
        ),
        FaultMode.SERVER_ERROR: FaultDecision("fault:server_error", "HTTP 503", 503),
    }
    return decisions[mode]


@dataclass(frozen=True)
class JournalEntry:
    monotonic_seconds: float
    method: str
    path: str
    query: str
    reason: str
    evidence: str
    headers: dict[str, str] | None = None


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    """Close a client connection, tolerating an already-reset peer."""
    writer.close()
    try:
        await writer.wait_closed()
    except BrokenPipeError, ConnectionResetError:
        pass


class ReplayApplication:
    """Exact router that records a redacted decision for every request."""

    def __init__(
        self,
        corpus: Corpus,
        *,
        mode: FaultMode,
        target_operation: str | None = None,
        barrier_entered: Path | None = None,
        barrier_release: Path | None = None,
        journal_path: Path | None = None,
    ) -> None:
        self._corpus = corpus
        self._mode = mode
        self._target_operation = target_operation
        self._release = asyncio.Event()
        self._barrier_entered = barrier_entered
        self._barrier_release = barrier_release
        self._journal_path = journal_path
        self.journal: list[JournalEntry] = []

    def release_barrier(self) -> None:
        """Release a request-entered barrier independently of mode selection."""
        self._release.set()

    def route(self, method: str, path: str, query: str) -> tuple[int, bytes]:
        fixture = self._match(method, path, query)
        if fixture is not None:
            self._record(method, path, query, "matched", "verified fixture")
            return fixture.status_code, fixture.file.read_bytes()
        self._record(method, path, query, "unexpected_request", "not in manifest")
        return 404, b""

    def _match(self, method: str, path: str, query: str) -> Fixture | None:
        query = canonical_query(query)
        return next(
            (
                fixture
                for fixture in self._corpus.fixtures
                if (fixture.method, fixture.path, fixture.query) == (method, path, query)
            ),
            None,
        )

    async def respond(
        self, method: str, path: str, query: str
    ) -> tuple[int | None, dict[str, str], bytes]:
        fixture = self._match(method, path, query)
        if fixture is None:
            self._record(method, path, query, "unexpected_request", "not in manifest")
            return 404, {}, b""
        if self._target_operation and fixture.sdk_operation != self._target_operation:
            self._record(method, path, query, "matched", "verified non-target fixture")
            return fixture.status_code, {}, fixture.file.read_bytes()
        decision = fault_decision(self._mode)
        if self._mode in {FaultMode.BASELINE, FaultMode.TRUSTED_TLS}:
            status, payload = self.route(method, path, query)
            return status, {}, payload
        if self._mode in {FaultMode.TIMEOUT, FaultMode.STALL}:
            self._record(method, path, query, decision.reason, decision.evidence)
            await self._wait_barrier(
                method,
                path,
                query,
                hold_seconds=STALL_HOLD_SECONDS if self._mode == FaultMode.STALL else 0,
            )
            return None, {}, b""
        if self._mode == FaultMode.SLOW_VALID:
            self._record(method, path, query, decision.reason, decision.evidence)
            await asyncio.sleep(2)
            status, payload = self.route(method, path, query)
            return status, {}, payload
        self._record(method, path, query, decision.reason, decision.evidence)
        if decision.transport_reset:
            return None, {}, b""
        headers = {"Retry-After": decision.retry_after} if decision.retry_after else {}
        payload = b"<html><body>failure</body></html>" if self._mode == FaultMode.HTML else b""
        return decision.status, headers, payload

    async def _wait_barrier(
        self, method: str, path: str, query: str, *, hold_seconds: float
    ) -> None:
        if self._barrier_entered:
            self._barrier_entered.write_text(f"{time.monotonic():.9f}\n", encoding="utf-8")
        self._record(
            method, path, query, "barrier:entered", "request reached deterministic barrier"
        )
        if hold_seconds:
            await asyncio.sleep(hold_seconds)
            self._record(
                method,
                path,
                query,
                "barrier:held",
                f"request remained blocked for {hold_seconds:.2f} seconds",
            )
        while not self._release.is_set() and not (
            self._barrier_release and self._barrier_release.exists()
        ):
            await asyncio.sleep(0.02)
        self._record(method, path, query, "barrier:released", "independent release observed")

    def _record(
        self,
        method: str,
        path: str,
        query: str,
        reason: str,
        evidence: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        entry = JournalEntry(
            time.monotonic(), method, path, canonical_query(query), reason, evidence, headers
        )
        self.journal.append(entry)
        if self._journal_path:
            with self._journal_path.open("a", encoding="utf-8") as journal:
                journal.write(json.dumps(asdict(entry), sort_keys=True) + "\n")


async def serve() -> None:
    """Run HTTPS origin, writing JSONL journal for host-side evidence collection."""
    mode = FaultMode(os.environ["HARNESS_MODE"])
    journal_path = Path(os.environ["HARNESS_JOURNAL"])
    app = ReplayApplication(
        load_manifest(Path(os.environ["HARNESS_MANIFEST"]), require_real=True),
        mode=mode,
        target_operation=os.environ.get("HARNESS_TARGET_OPERATION") or None,
        barrier_entered=Path(os.environ["HARNESS_BARRIER_ENTERED"]),
        barrier_release=Path(os.environ["HARNESS_BARRIER_RELEASE"]),
        journal_path=journal_path,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(os.environ["HARNESS_TLS_CERT"], os.environ["HARNESS_TLS_KEY"])

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            method, target, _ = request.split(b"\r\n", 1)[0].decode().split(" ", 2)
            path, _, query = target.partition("?")
            status, headers, payload = await app.respond(method, path, query)
            if status is None:
                if fault_decision(mode).transport_reset:
                    app._record(method, path, query, "transport:aborted", "connection abort sent")
                writer.transport.abort()
                return
            reason = {
                200: "OK",
                401: "Unauthorized",
                403: "Forbidden",
                404: "Not Found",
                429: "Too Many Requests",
                502: "Bad Gateway",
                503: "Service Unavailable",
            }.get(status, "Failure")
            response_headers = {
                "Content-Length": str(len(payload)),
                "Connection": "close",
                **headers,
            }
            if payload.startswith(b"<html"):
                response_headers["Content-Type"] = "text/html"
            wire = (
                f"HTTP/1.1 {status} {reason}\r\n"
                + "".join(f"{k}: {v}\r\n" for k, v in response_headers.items())
                + "\r\n"
            )
            writer.write(wire.encode() + payload)
            await writer.drain()
            app._record(
                method, path, query, "response:sent", f"HTTP {status} response sent", headers
            )
        except asyncio.IncompleteReadError, ValueError:
            return
        finally:
            await _close_writer(writer)

    server = await asyncio.start_server(handle, "0.0.0.0", 9443, ssl=context)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(serve())
