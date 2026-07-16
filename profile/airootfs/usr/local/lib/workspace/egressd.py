#!/usr/bin/env python3
"""Audited HTTPS-only acquisition broker for offline LGA workers."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import socketserver
import ssl
import tempfile
import threading
import uuid
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

from workspace_policy import PolicyError, bounded_int, load_policy


CHUNK_SIZE = 64 * 1024
MAX_REQUEST_BYTES = 64 * 1024
REDIRECT_CODES = {301, 302, 303, 307, 308}
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class EgressError(ValueError):
    """A request violates egress policy or failed safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitized_url(parts: SplitResult) -> str:
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port and port != 443 else host
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def validate_url(url: str, allowed_hosts: set[str]) -> tuple[SplitResult, list[str]]:
    if len(url) > 8192 or "\x00" in url:
        raise EgressError("URL is too long or contains NUL")
    parts = urlsplit(url)
    if parts.scheme.lower() != "https":
        raise EgressError("only HTTPS URLs are allowed")
    if parts.username is not None or parts.password is not None:
        raise EgressError("credentials in URLs are forbidden")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or host not in allowed_hosts:
        raise EgressError(f"host is not allowlisted: {host or '<empty>'}")
    try:
        port = parts.port or 443
    except ValueError as exc:
        raise EgressError("invalid URL port") from exc
    if port != 443:
        raise EgressError("only TCP port 443 is allowed")
    try:
        addresses = sorted(
            {
                str(item[4][0])
                for item in socket.getaddrinfo(
                    host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
                )
            }
        )
    except socket.gaierror as exc:
        raise EgressError(f"DNS resolution failed for {host}: {exc}") from exc
    if not addresses:
        raise EgressError("DNS returned no address")
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise EgressError(f"DNS returned invalid address: {address}") from exc
        if not parsed.is_global:
            raise EgressError(f"non-global destination is forbidden: {address}")
    return parts, addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a prevalidated IP while retaining hostname TLS verification."""

    def __init__(self, host: str, address: str, *, timeout: float) -> None:
        self._workspace_context = ssl.create_default_context()
        super().__init__(host=host, port=443, timeout=timeout, context=self._workspace_context)
        self._pinned_address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._pinned_address, 443), self.timeout)
        self.sock = self._workspace_context.wrap_socket(raw, server_hostname=self.host)


class Fetcher:
    def __init__(self, policy: dict[str, Any]) -> None:
        config = policy["egress"]
        hosts = config.get("allowed_hosts")
        if not isinstance(hosts, list) or not hosts or not all(isinstance(x, str) for x in hosts):
            raise PolicyError("egress.allowed_hosts must be a non-empty string list")
        self.allowed_hosts = {host.lower().rstrip(".") for host in hosts}
        self.max_bytes = bounded_int(
            config.get("max_bytes"), name="egress.max_bytes", minimum=1, maximum=2**32
        )
        self.max_quarantine_bytes = bounded_int(
            config.get("max_quarantine_bytes"),
            name="egress.max_quarantine_bytes",
            minimum=1,
            maximum=2**44,
        )
        self.max_audit_bytes = bounded_int(
            config.get("max_audit_bytes"),
            name="egress.max_audit_bytes",
            minimum=1024,
            maximum=2**34,
        )
        self.timeout = bounded_int(
            config.get("timeout_seconds"),
            name="egress.timeout_seconds",
            minimum=1,
            maximum=300,
        )
        self.user_agent = str(config.get("user_agent") or "WorkSpace-Egress/0.1")

    def _request(self, url: str) -> tuple[http.client.HTTPResponse, SplitResult]:
        parts, addresses = validate_url(url, self.allowed_hosts)
        host = (parts.hostname or "").lower().rstrip(".")
        target = parts.path or "/"
        if parts.query:
            target += f"?{parts.query}"
        last_error: Exception | None = None
        for address in addresses:
            connection = PinnedHTTPSConnection(host, address, timeout=self.timeout)
            try:
                connection.request(
                    "GET",
                    target,
                    headers={
                        "Accept": "*/*",
                        "Host": host,
                        "User-Agent": self.user_agent,
                    },
                )
                response = connection.getresponse()
                # HTTPResponse retains the connection/socket until fully read.
                response._workspace_connection = connection  # type: ignore[attr-defined]
                return response, parts
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                connection.close()
                last_error = exc
        raise EgressError(f"all validated destinations failed: {last_error}")

    def fetch(
        self,
        url: str,
        quarantine: Path,
        *,
        expected_sha256: str | None = None,
        existing_quarantine_bytes: int = 0,
    ) -> dict[str, Any]:
        current = url
        response: http.client.HTTPResponse | None = None
        parts: SplitResult | None = None
        for _ in range(6):
            response, parts = self._request(current)
            if response.status not in REDIRECT_CODES:
                break
            location = response.getheader("Location")
            response.read()
            response.close()
            if not location:
                raise EgressError("redirect response omitted Location")
            current = urljoin(current, location)
            validate_url(current, self.allowed_hosts)
        else:
            raise EgressError("too many redirects")
        assert response is not None and parts is not None
        try:
            if response.status != 200:
                response.read(min(self.max_bytes, 4096))
                raise EgressError(f"upstream returned HTTP {response.status}")
            length = response.getheader("Content-Length")
            if length is not None:
                try:
                    announced = int(length)
                except ValueError as exc:
                    raise EgressError("invalid Content-Length") from exc
                if announced < 0 or announced > self.max_bytes:
                    raise EgressError("response exceeds configured size")
            quarantine.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            total = 0
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    prefix=".download-", suffix=".part", dir=quarantine, delete=False
                ) as output:
                    temporary = Path(output.name)
                    while chunk := response.read(CHUNK_SIZE):
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise EgressError("response exceeded configured size while streaming")
                        if existing_quarantine_bytes + total > self.max_quarantine_bytes:
                            raise EgressError("quarantine capacity would be exceeded")
                        output.write(chunk)
                        digest.update(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                actual = digest.hexdigest()
                if expected_sha256 and actual != expected_sha256.lower():
                    raise EgressError("download hash does not match expected_sha256")
                leaf = Path(parts.path).name or "download.bin"
                leaf = SAFE_NAME.sub("_", leaf)[:96] or "download.bin"
                destination = quarantine / f"{actual[:16]}-{leaf}"
                if destination.exists():
                    temporary.unlink(missing_ok=True)
                else:
                    os.chmod(temporary, 0o640)
                    os.replace(temporary, destination)
                temporary = None
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return {
                "status": "quarantined",
                "url": sanitized_url(parts),
                "path": str(destination),
                "sha256": actual,
                "size": total,
                "media_type": (response.getheader("Content-Type") or "application/octet-stream").split(";", 1)[0],
            }
        finally:
            response.close()


class Broker:
    def __init__(self, policy: dict[str, Any], quarantine: Path, audit_path: Path) -> None:
        self.fetcher = Fetcher(policy)
        self.quarantine = quarantine
        self.audit_path = audit_path
        self._audit_lock = threading.Lock()
        self._fetch_lock = threading.Lock()

    def _quarantine_usage(self) -> int:
        total = 0
        if not self.quarantine.exists():
            return 0
        for path in self.quarantine.iterdir():
            if path.is_file() and not path.is_symlink() and not path.name.startswith(".download-"):
                total += path.stat().st_size
        return total

    def _audit(self, record: dict[str, Any]) -> None:
        record = {"at": utc_now(), **record}
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with self._audit_lock:
            if self.audit_path.exists() and self.audit_path.stat().st_size + len(line.encode("utf-8")) > self.fetcher.max_audit_bytes:
                rotated = self.audit_path.with_suffix(self.audit_path.suffix + ".1")
                rotated.unlink(missing_ok=True)
                os.replace(self.audit_path, rotated)
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self.audit_path, flags, 0o640)
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = str(request.get("request_id") or uuid.uuid4())
        url = request.get("url")
        if not isinstance(url, str):
            raise EgressError("url must be a string")
        expected = request.get("expected_sha256")
        if expected is not None:
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
                raise EgressError("expected_sha256 must be 64 hexadecimal characters")
        try:
            with self._fetch_lock:
                result = self.fetcher.fetch(
                    url,
                    self.quarantine,
                    expected_sha256=expected,
                    existing_quarantine_bytes=self._quarantine_usage(),
                )
            self._audit(
                {
                    "request_id": request_id,
                    "outcome": "allow",
                    "url": result["url"],
                    "sha256": result["sha256"],
                    "size": result["size"],
                }
            )
            return {"ok": True, "request_id": request_id, **result}
        except Exception as exc:
            try:
                parts = urlsplit(url)
                log_url = sanitized_url(parts)
            except Exception:
                log_url = "<invalid>"
            self._audit(
                {
                    "request_id": request_id,
                    "outcome": "deny",
                    "url": log_url,
                    "error": str(exc),
                }
            )
            raise


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            self._send({"ok": False, "error": "request exceeds limit"})
            return
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise EgressError("request must be a JSON object")
            result = self.server.broker.handle(data)  # type: ignore[attr-defined]
            self._send(result)
        except (UnicodeDecodeError, json.JSONDecodeError, EgressError, PolicyError, OSError) as exc:
            self._send({"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        except Exception as exc:  # keep the protocol alive without leaking internals
            self._send({"ok": False, "error": "broker request failed", "error_type": type(exc).__name__})

    def _send(self, payload: dict[str, Any]) -> None:
        self.wfile.write(
            (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        )


class ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 16
    allow_reuse_address = True


def serve(socket_path: Path, broker: Broker) -> None:
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists() or socket_path.is_symlink():
        if socket_path.parent != Path("/run/lga"):
            raise EgressError("refusing to remove socket outside /run/lga")
        socket_path.unlink()
    with ThreadingUnixServer(str(socket_path), RequestHandler) as server:
        server.broker = broker  # type: ignore[attr-defined]
        os.chmod(socket_path, 0o660)
        server.serve_forever(poll_interval=0.5)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lga-egressd")
    parser.add_argument("--policy", type=Path, default=Path("/etc/lga/policy.toml"))
    parser.add_argument("--socket", type=Path, default=Path("/run/lga/egress.sock"))
    parser.add_argument(
        "--quarantine", type=Path, default=Path("/var/lib/lga/quarantine")
    )
    parser.add_argument(
        "--audit", type=Path, default=Path("/var/lib/lga/audit/egress.jsonl")
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        policy = load_policy(args.policy)
        serve(args.socket, Broker(policy, args.quarantine, args.audit))
        return 0
    except (EgressError, PolicyError, OSError) as exc:
        print(f"lga-egressd: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
