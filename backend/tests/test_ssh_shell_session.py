"""SSHShellSession is what backs the web CLI's persistent session for
every vendor (Palo Alto/Fortigate/Cisco all subclass it). These tests
fake out paramiko entirely so they run without a real device, but
exercise the exact behaviors that were broken before this fix:
keepalive not being set, output arriving after the old fixed 1s sleep
getting dropped, and a mid-session failure crashing instead of
surfacing a clear error.
"""
import time
import pytest
import paramiko

from app.drivers.base import SSHShellSession


class FakeTransport:
    def __init__(self):
        self.keepalive_seconds = None

    def set_keepalive(self, seconds):
        self.keepalive_seconds = seconds


class FakeChannel:
    def __init__(self, chunks=None, closed=False):
        # chunks: list of (delay_seconds, bytes) delivered in order
        self._chunks = list(chunks or [])
        self._sent = []
        self.closed = closed
        self._timeout = None

    def settimeout(self, value):
        self._timeout = value

    def send(self, data):
        self._sent.append(data)

    def recv_ready(self):
        return bool(self._chunks) and self._chunks[0][0] <= 0

    def recv(self, _size):
        delay, data = self._chunks.pop(0)
        return data

    def tick(self, elapsed):
        # advance simulated time for pending chunk delays
        self._chunks = [(max(0, d - elapsed), b) for d, b in self._chunks]


class FakeSSHClient:
    instances = []

    def __init__(self):
        self.connected_to = None
        self._transport = FakeTransport()
        self.channel = FakeChannel()
        FakeSSHClient.instances.append(self)

    def set_missing_host_key_policy(self, policy):
        pass

    def connect(self, host, username, password, timeout):
        self.connected_to = host

    def get_transport(self):
        return self._transport

    def invoke_shell(self):
        return self.channel

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_paramiko(monkeypatch):
    FakeSSHClient.instances.clear()
    monkeypatch.setattr(paramiko, "SSHClient", FakeSSHClient)
    yield


def test_connect_sets_ssh_keepalive():
    session = SSHShellSession("10.0.0.1", "admin", "secret")
    client = FakeSSHClient.instances[0]
    assert client._transport.keepalive_seconds == SSHShellSession._KEEPALIVE_INTERVAL_SECONDS


def test_send_command_waits_past_one_second_for_slow_output(monkeypatch):
    # Simulate a slow command: nothing ready for 1.5s (past the old
    # fixed 1s sleep), then output arrives. The old implementation
    # would have returned "" here.
    session = SSHShellSession("10.0.0.1", "admin", "secret")
    client = FakeSSHClient.instances[0]
    client.channel._chunks = [(1.5, b"slow output\n")]

    real_monotonic = time.monotonic
    state = {"t": real_monotonic()}
    monkeypatch.setattr(time, "monotonic", lambda: state["t"])

    def fake_sleep(seconds):
        state["t"] += seconds
        client.channel.tick(seconds)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    output = session.send_command("show version")
    assert "slow output" in output


def test_send_command_raises_connection_error_when_channel_closed():
    session = SSHShellSession("10.0.0.1", "admin", "secret")
    client = FakeSSHClient.instances[0]
    client.channel.closed = True

    with pytest.raises(ConnectionError):
        session.send_command("show version")


def test_connect_failure_raises_clear_connection_error(monkeypatch):
    class FailingClient(FakeSSHClient):
        def connect(self, host, username, password, timeout):
            raise OSError("no route to host")

    monkeypatch.setattr(paramiko, "SSHClient", FailingClient)
    with pytest.raises(ConnectionError):
        SSHShellSession("10.0.0.1", "admin", "secret")
