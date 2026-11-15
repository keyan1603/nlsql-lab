"""Egress proof: record, and in sealed mode refuse, every outbound network connection a Python process tries to make.

The data-residency claim of the hybrid pipeline is "in sealed mode nothing leaves the machine". A policy flag in our own code is not
evidence for that, because a bug could bypass the flag. This module is the independent check: it wraps the socket layer that every
network client in the Python standard library (urllib, http.client, ssl) and PyMySQL sit on, logs each attempt with its destination,
and in sealed mode raises before anything is sent when the destination is not on the allow-list.

What counts as allowed in sealed mode:
  * loopback addresses (127.0.0.0/8, ::1) and the name "localhost" (LM Studio's server lives here)
  * the MySQL host and port from nlsql.config (the database is inside the boundary by definition; with the default
    settings that is loopback too, so the allow-list is then loopback only)

What is wrapped, and why each one:
  socket.getaddrinfo      a DNS lookup of a public name already tells the resolver which service we are about to call, so it is
                          refused in sealed mode like a connection would be. IP literals need no lookup and pass through the
                          same address check.
  socket.create_connection, socket.socket.connect, socket.socket.connect_ex
                          the connection attempts themselves (create_connection is what urllib and PyMySQL call; connect is
                          the lowest level any Python-level client reaches; connect_ex is the non-raising variant)
  socket.socket.sendto    UDP can send without ever calling connect

What is NOT covered (stated so nobody over-reads the proof): a subprocess started by this process (it has its own sockets), a C
extension that opens a socket without going through the socket module, and anything outside this Python process. For this
pipeline the only extensions are PyMySQL (pure Python) and sqlglot (pure Python). The report says which mode ran and lists
every destination that was allowed.

EgressBlocked is deliberately NOT an OSError. nlsql/llm_gemini.py retries on OSError with sleeps; a policy violation must stop at
once, not be retried six times.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import threading
from collections import Counter
from contextlib import AbstractContextManager
from pathlib import Path

LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


class EgressBlocked(Exception):
    """A connection or lookup to a destination outside the allow-list was attempted in sealed mode."""


def _is_loopback(host: str) -> bool:
    """True for a loopback IP literal or a loopback host name. Never resolves anything."""
    h = (host or "").strip().strip("[]").lower()
    if h in LOOPBACK_NAMES:
        return True
    h = h.split("%", 1)[0]                                  # an IPv6 zone id such as fe80::1%eth0
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _mysql_endpoint() -> tuple[str, int]:
    """The configured MySQL (host, port). Falls back to the loopback default when settings cannot be loaded (for example no .env)."""
    try:
        from nlsql.config import load_settings
        s = load_settings()
        return s.host, int(s.port)
    except Exception:
        return "127.0.0.1", 3306


def _split(address) -> tuple[str, int | None]:
    """(host, port) from the address forms the socket module uses: (host, port) or (host, port, flowinfo, scope_id)."""
    if isinstance(address, (tuple, list)) and address:
        host = address[0]
        port = address[1] if len(address) > 1 else None
        return (host.decode() if isinstance(host, bytes) else str(host)), (int(port) if isinstance(port, (int, str)) and str(port).isdigit() else None)
    return str(address), None                               # AF_UNIX path or something unexpected: recorded as-is, judged below


class EgressMonitor(AbstractContextManager):
    """Context manager. mode='sealed' refuses non-allow-listed destinations; mode='observe' only records (used to show what an
    open-policy run talks to). Entering patches the socket module for the whole process; leaving restores it exactly."""

    def __init__(self, mode: str = "sealed", mysql: tuple[str, int] | None = None):
        if mode not in ("sealed", "observe"):
            raise ValueError("mode must be 'sealed' or 'observe'")
        self.mode = mode
        self.mysql = mysql or _mysql_endpoint()
        self._lock = threading.Lock()
        self._allowed: Counter = Counter()      # (kind, host, port) -> count
        self._blocked: Counter = Counter()
        self._originals: dict = {}

    # ---- decision
    def _permitted(self, host: str, port: int | None) -> bool:
        if _is_loopback(host):
            return True
        return host == self.mysql[0] and (port is None or port == self.mysql[1])

    def _check(self, kind: str, address) -> None:
        host, port = _split(address)
        key = (kind, host, port)
        if self._permitted(host, port):
            with self._lock:
                self._allowed[key] += 1
            return
        with self._lock:
            # In observe mode a non-allow-listed destination is still recorded, under 'blocked' only when sealed
            (self._blocked if self.mode == "sealed" else self._allowed)[key] += 1
        if self.mode == "sealed":
            raise EgressBlocked(f"sealed mode: {kind} to {host}:{port} refused (not loopback and not the MySQL endpoint {self.mysql[0]}:{self.mysql[1]})")

    # ---- patching
    def __enter__(self):
        mon, orig = self, self._originals
        orig["getaddrinfo"], orig["create_connection"] = socket.getaddrinfo, socket.create_connection
        orig["connect"], orig["connect_ex"], orig["sendto"] = socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto

        def getaddrinfo(host, port, *a, **kw):
            if host not in (None, "", b""):
                mon._check("dns", (host, port))
            return orig["getaddrinfo"](host, port, *a, **kw)

        def create_connection(address, *a, **kw):
            mon._check("create_connection", address)
            return orig["create_connection"](address, *a, **kw)

        def connect(self, address):
            mon._check("connect", address)
            return orig["connect"](self, address)

        def connect_ex(self, address):
            mon._check("connect_ex", address)
            return orig["connect_ex"](self, address)

        def sendto(self, data, *args):
            mon._check("sendto", args[-1])                  # the destination is the last argument in both call forms
            return orig["sendto"](self, data, *args)

        socket.getaddrinfo, socket.create_connection = getaddrinfo, create_connection
        socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto = connect, connect_ex, sendto
        return self

    def __exit__(self, *exc):
        o = self._originals
        socket.getaddrinfo, socket.create_connection = o["getaddrinfo"], o["create_connection"]
        socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto = o["connect"], o["connect_ex"], o["sendto"]
        return False

    def clear(self) -> None:
        """Forget what was recorded so far (used after the start-up canary, whose deliberate blocked attempt is reported separately)."""
        with self._lock:
            self._allowed.clear()
            self._blocked.clear()

    # ---- reporting
    @staticmethod
    def _rows(counter: Counter) -> list[dict]:
        return [{"kind": k, "host": h, "port": p, "count": n} for (k, h, p), n in sorted(counter.items(), key=lambda kv: (kv[0][1], str(kv[0][2]), kv[0][0]))]

    def report(self) -> dict:
        with self._lock:
            allowed, blocked = self._rows(self._allowed), self._rows(self._blocked)
        non_loopback = [r for r in allowed if not _is_loopback(r["host"])]
        return {"mode": self.mode, "mysql_endpoint": f"{self.mysql[0]}:{self.mysql[1]}",
                "attempts_total": sum(r["count"] for r in allowed) + sum(r["count"] for r in blocked),
                "allowed": allowed, "blocked": blocked,
                # In sealed mode non_loopback_allowed can only contain the MySQL endpoint, and only when it is not loopback itself.
                "non_loopback_allowed": non_loopback,
                "blocked_count": sum(r["count"] for r in blocked)}

    def write_report(self, path: Path) -> dict:
        rep = self.report()
        Path(path).write_text(json.dumps(rep, indent=2), encoding="utf-8")
        return rep
