"""
Every vendor driver (PaloAltoDriver, FortigateDriver, and later
CiscoIOSRouterDriver / CiscoIOSSwitchDriver) implements this same
interface. Nothing outside the driver layer should call vendor SDKs
or parse vendor-specific CLI output directly -- that logic lives here,
once per vendor, and nowhere else.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models import (
    Device,
    Interface,
    RouteEntry,
    MacArpEntry,
    Session,
    PolicyRule,
    LogEvent,
    HealthSnapshot,
)


class CLISession(ABC):
    """A live, interactive CLI session to a device, used by the web
    terminal and the native CLI client. Full, unrestricted access --
    not a limited show-only shell."""

    @abstractmethod
    def send_command(self, command: str) -> str:
        ...

    @abstractmethod
    def close(self) -> None:
        ...


class SSHShellSession(CLISession):
    """Shared, real interactive SSH session used by every vendor's CLI
    driver (Palo Alto, Fortigate, Cisco IOS previously each duplicated
    this exact logic). Two real-world fixes over the old per-vendor
    versions:

    1. SSH keepalive -- without it, a device or anything in the network
       path (firewall session table, NAT) that silently drops an idle
       TCP connection leaves paramiko unaware until the next read/write
       fails, which surfaces as the whole CLI session dying with no
       explanation. `set_keepalive` sends a lightweight packet on an
       interval so a dead connection is detected (and can raise a
       clear error) instead of just going silent.

    2. Bounded polling loop instead of one fixed `sleep(1)` -- a command
       that takes longer than a second (a full `show tech-support`, a
       big routing table) came back truncated or blank before, and a
       fast command wasted up to a second doing nothing. This waits
       for output to actually stop arriving (a short quiet period),
       up to an overall cap, so both cases behave correctly.
    """

    # How long to keep reading after the last byte arrives before
    # deciding the device is done responding.
    _QUIET_PERIOD_SECONDS = 0.4
    # Hard ceiling per command, so one hung/very slow command can't
    # block the terminal forever.
    _MAX_WAIT_SECONDS = 20
    # How often the underlying transport sends a keepalive packet.
    _KEEPALIVE_INTERVAL_SECONDS = 30

    def __init__(self, host: str, username: str, password: str):
        import paramiko
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._client.connect(host, username=username, password=password, timeout=10)
        except Exception as exc:  # noqa: BLE001 -- surface a clear connect failure, not a bare paramiko traceback
            raise ConnectionError(f"SSH connection to {host} failed: {exc}") from exc
        transport = self._client.get_transport()
        if transport is not None:
            transport.set_keepalive(self._KEEPALIVE_INTERVAL_SECONDS)
        self._shell = self._client.invoke_shell()
        self._shell.settimeout(self._MAX_WAIT_SECONDS)

    def send_command(self, command: str) -> str:
        import socket
        import time
        if self._shell.closed:
            raise ConnectionError("CLI session is closed -- reconnect required")
        try:
            self._shell.send(command + "\n")
        except OSError as exc:
            raise ConnectionError(f"Failed to send command -- session may have dropped: {exc}") from exc

        output = ""
        deadline = time.monotonic() + self._MAX_WAIT_SECONDS
        last_data_at = None
        while time.monotonic() < deadline:
            if self._shell.recv_ready():
                try:
                    chunk = self._shell.recv(65535)
                except socket.timeout:
                    break
                if not chunk:
                    # Remote end closed the channel.
                    raise ConnectionError("Device closed the SSH session")
                output += chunk.decode(errors="ignore")
                last_data_at = time.monotonic()
            elif last_data_at is not None and time.monotonic() - last_data_at >= self._QUIET_PERIOD_SECONDS:
                # Output has started and then stopped -- the device is
                # done responding. Before any data has arrived at all,
                # keep waiting up to the full deadline instead, since a
                # slower command just hasn't started replying yet.
                break
            else:
                time.sleep(0.05)
        return output

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 -- best-effort cleanup, never raise on close
            pass


class DriverNotSupported(NotImplementedError):
    """Raised when a method doesn't apply to this device type
    (e.g. test_policy_match on a switch)."""


class DeviceDriver(ABC):
    """Abstract vendor driver. device is the normalized Device record
    this driver instance is bound to; credentials are resolved from
    the vault via device.credential_ref, never passed in plaintext."""

    def __init__(self, device: Device, credential: dict):
        self.device = device
        self._credential = credential  # {"username": ..., "password"/"api_key": ...}

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def get_facts(self) -> Device:
        ...

    @abstractmethod
    def get_interfaces(self) -> list[Interface]:
        ...

    def get_route(self, destination_ip: str) -> list[RouteEntry]:
        raise DriverNotSupported(f"{type(self).__name__} does not support routing tables")

    def get_arp_mac_table(self) -> list[MacArpEntry]:
        raise DriverNotSupported(f"{type(self).__name__} does not support ARP/MAC tables")

    def get_sessions(self, src_ip: Optional[str] = None, dst_ip: Optional[str] = None) -> list[Session]:
        raise DriverNotSupported(f"{type(self).__name__} does not support session lookup")

    def test_policy_match(self, src_ip: str, dst_ip: str, port: int, proto: str) -> Optional[PolicyRule]:
        raise DriverNotSupported(f"{type(self).__name__} does not support policy-match testing")

    def get_policy_rules(self) -> list[PolicyRule]:
        raise DriverNotSupported(f"{type(self).__name__} does not support policy listing")

    def get_neighbors(self) -> list:
        """CDP/LLDP neighbor discovery, used by the topology engine.
        Optional -- not every device type needs to implement it.
        Returns list[DiscoveredNeighbor]."""
        raise DriverNotSupported(f"{type(self).__name__} does not support neighbor discovery")

    def get_licenses(self) -> list:
        """Real license/entitlement data from the device itself.
        Optional -- implemented for firewalls (PAN-OS, FortiOS) where
        there's a clean vendor API for it; not yet for Cisco IOS.
        Returns list[License]."""
        raise DriverNotSupported(f"{type(self).__name__} does not support license queries")

    def get_running_config(self) -> str:
        """Real full running configuration as raw text/XML, straight
        from the device -- for Configuration Backup. Optional in the
        interface but implemented for every vendor this platform
        supports; a device type without a meaningful "config" concept
        (an AP, say) would leave this unimplemented."""
        raise DriverNotSupported(f"{type(self).__name__} does not support config backup")

    @abstractmethod
    def get_logs(self, filters: dict, time_range: tuple) -> list[LogEvent]:
        ...

    @abstractmethod
    def health_check(self) -> HealthSnapshot:
        ...

    @abstractmethod
    def open_cli_session(self) -> CLISession:
        ...
