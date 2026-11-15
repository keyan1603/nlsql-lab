"""Offline tests for nlsql.egress. No real connection is ever made: the socket functions the monitor wraps are replaced by recorders
BEFORE the monitor is entered, so if a wrapper failed to block, the recorder (not the network) would receive the call and the
test would still fail on the assertion."""
import socket

import pytest

from nlsql.egress import EgressBlocked, EgressMonitor, _is_loopback


@pytest.fixture
def fake_net(monkeypatch):
    """Replace the real socket entry points with recorders; return the list of calls that got through to them."""
    through = []
    monkeypatch.setattr(socket, "create_connection", lambda address, *a, **k: through.append(("create_connection", address)) or "sock")
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: through.append(("getaddrinfo", host)) or [])
    monkeypatch.setattr(socket.socket, "connect", lambda self, address: through.append(("connect", address)))
    monkeypatch.setattr(socket.socket, "connect_ex", lambda self, address: through.append(("connect_ex", address)) or 0)
    monkeypatch.setattr(socket.socket, "sendto", lambda self, data, *args: through.append(("sendto", args[-1])) or len(data))
    return through


def test_sealed_blocks_a_public_ip_and_nothing_reaches_the_socket(fake_net):
    with EgressMonitor("sealed", mysql=("127.0.0.1", 3306)) as mon:
        with pytest.raises(EgressBlocked):
            socket.create_connection(("8.8.8.8", 443))
        s = socket.socket()
        with pytest.raises(EgressBlocked):
            s.connect(("142.250.80.42", 443))
        with pytest.raises(EgressBlocked):
            s.connect_ex(("142.250.80.42", 443))
        with pytest.raises(EgressBlocked):
            s.sendto(b"x", ("8.8.8.8", 53))
        s.close()
    assert fake_net == []                                              # not one call got through
    rep = mon.report()
    assert rep["blocked_count"] == 4 and rep["allowed"] == [] and rep["mode"] == "sealed"
    assert {b["host"] for b in rep["blocked"]} == {"8.8.8.8", "142.250.80.42"}


def test_sealed_blocks_a_public_hostname_at_the_dns_lookup(fake_net):
    with EgressMonitor("sealed", mysql=("127.0.0.1", 3306)) as mon:
        with pytest.raises(EgressBlocked):
            socket.getaddrinfo("generativelanguage.googleapis.com", 443)
        with pytest.raises(EgressBlocked):
            socket.create_connection(("generativelanguage.googleapis.com", 443))
    assert fake_net == []
    assert mon.report()["blocked"][0]["host"] == "generativelanguage.googleapis.com"


def test_sealed_allows_and_records_loopback(fake_net):
    with EgressMonitor("sealed", mysql=("127.0.0.1", 3306)) as mon:
        socket.create_connection(("127.0.0.1", 1235))
        socket.create_connection(("localhost", 1235))
        socket.socket().connect(("::1", 1235, 0, 0))                 # IPv6 address tuples have four fields
    rep = mon.report()
    assert rep["blocked_count"] == 0 and rep["non_loopback_allowed"] == []
    assert {a["host"] for a in rep["allowed"]} == {"127.0.0.1", "localhost", "::1"}
    assert ("create_connection", ("127.0.0.1", 1235)) in fake_net      # allowed calls do pass through to the real function


def test_sealed_allows_the_configured_mysql_endpoint_only_on_its_port(fake_net):
    with EgressMonitor("sealed", mysql=("db.internal", 3306)) as mon:
        socket.create_connection(("db.internal", 3306))
        with pytest.raises(EgressBlocked):
            socket.create_connection(("db.internal", 8080))            # same host, other port
        with pytest.raises(EgressBlocked):
            socket.create_connection(("other.internal", 3306))         # same port, other host
    rep = mon.report()
    assert rep["non_loopback_allowed"] and rep["non_loopback_allowed"][0]["host"] == "db.internal"
    assert rep["blocked_count"] == 2


def test_observe_mode_records_but_does_not_block(fake_net):
    with EgressMonitor("observe", mysql=("127.0.0.1", 3306)) as mon:
        socket.create_connection(("8.8.8.8", 443))
    rep = mon.report()
    assert rep["blocked_count"] == 0 and [r["host"] for r in rep["non_loopback_allowed"]] == ["8.8.8.8"]
    assert ("create_connection", ("8.8.8.8", 443)) in fake_net


def test_the_socket_module_is_restored_on_exit_even_after_an_exception(fake_net):
    before = (socket.create_connection, socket.getaddrinfo, socket.socket.connect)
    with pytest.raises(EgressBlocked):
        with EgressMonitor("sealed", mysql=("127.0.0.1", 3306)):
            socket.create_connection(("8.8.8.8", 443))
    assert (socket.create_connection, socket.getaddrinfo, socket.socket.connect) == before


def test_egress_blocked_is_not_an_oserror_so_retry_loops_do_not_swallow_it():
    assert not issubclass(EgressBlocked, OSError)


def test_a_url_fetch_to_a_public_host_is_blocked_before_any_bytes_are_sent(fake_net):
    """The same path llm_gemini takes: urllib -> http.client -> socket.create_connection. Blocked at the first hop."""
    import urllib.request
    with EgressMonitor("sealed", mysql=("127.0.0.1", 3306)) as mon:
        with pytest.raises(EgressBlocked):
            urllib.request.urlopen("https://generativelanguage.googleapis.com/v1beta/models", timeout=2)
    assert fake_net == [] and mon.report()["blocked_count"] >= 1


@pytest.mark.parametrize("host,expected", [("127.0.0.1", True), ("127.5.5.5", True), ("::1", True), ("[::1]", True), ("localhost", True),
                                          ("LOCALHOST", True), ("8.8.8.8", False), ("192.168.1.10", False), ("10.0.0.1", False), ("example.com", False), ("", False)])
def test_loopback_classification(host, expected):
    assert _is_loopback(host) is expected


def test_report_is_written_as_json(tmp_path, fake_net):
    with EgressMonitor("sealed", mysql=("127.0.0.1", 3306)) as mon:
        socket.create_connection(("127.0.0.1", 1235))
    rep = mon.write_report(tmp_path / "egress.json")
    assert (tmp_path / "egress.json").exists() and rep["attempts_total"] >= 1
