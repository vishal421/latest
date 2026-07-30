"""
Cisco IOS/IOS-XE driver.

Unlike Palo Alto and Fortigate, there's no clean REST API to lean on
here for most devices in the field -- this driver is SSH/CLI-based
throughout (the pattern Netmiko/NAPALM use), parsing `show` command
text output. Exact output formatting varies by IOS/IOS-XE version and
device family, so the regexes below target a mainstream IOS-XE
release and should be checked against your lab devices.

Router and switch share almost everything (facts, interfaces, health,
CLI session, neighbor discovery) -- they differ only in get_route
(router-only) and get_arp_mac_table (switch-only), so both live in one
base class with the differing pieces in subclasses.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from app.models import (
    Device, Interface, RouteEntry, MacArpEntry, LogEvent, LogEventType,
    HealthSnapshot, DiscoveredNeighbor,
)
from app.drivers.base import DeviceDriver, CLISession, SSHShellSession, DriverNotSupported


_PROTO_NUM_TO_NAME = {1: "icmp", 6: "tcp", 17: "udp", 47: "gre", 50: "esp"}


class CiscoIOSCLISession(SSHShellSession):
    """IOS/IOS-XE needs one vendor-specific step the other CLIs don't:
    disabling --More-- paging, or a `show` command longer than one
    screen would hang waiting for a keypress that never comes."""

    def __init__(self, host: str, username: str, password: str):
        super().__init__(host, username, password)
        self.send_command("terminal length 0")


class CiscoIOSDriverBase(DeviceDriver):
    """Shared implementation for router and switch. Subclasses set
    the device_type-specific methods (get_route / get_arp_mac_table)."""

    def __init__(self, device: Device, credential: dict, cli_session_factory=None):
        super().__init__(device, credential)
        # Injectable for tests -- avoids opening a real SSH connection.
        self._cli_session_factory = cli_session_factory or (
            lambda: CiscoIOSCLISession(device.mgmt_ip, credential["username"], credential["password"])
        )
        self._session: Optional[CLISession] = None

    def connect(self) -> None:
        if self._session is None:
            self._session = self._cli_session_factory()

    def _run(self, command: str) -> str:
        self.connect()
        return self._session.send_command(command)

    def get_facts(self) -> Device:
        output = self._run("show version")
        model_m = re.search(r"[Cc]isco\s+(\S+)\s+\(.*?\)\s+processor", output)
        version_m = re.search(r"Version\s+([\d.\w()]+)", output)
        serial_m = re.search(r"[Pp]rocessor board ID\s+(\S+)", output)
        hostname_m = re.search(r"^(\S+)\s+uptime is", output, re.MULTILINE)

        if model_m:
            self.device.model = model_m.group(1)
        if version_m:
            self.device.os_version = version_m.group(1)
        if serial_m:
            self.device.serial_number = serial_m.group(1)
        if hostname_m:
            self.device.hostname = hostname_m.group(1)
        self.device.last_seen = datetime.utcnow()
        return self.device

    def get_interfaces(self) -> list[Interface]:
        brief_output = self._run("show ip interface brief")
        counters_output = self._run("show interfaces")

        interfaces = []
        brief_lines = {}
        for line in brief_output.splitlines():
            m = re.match(r"^(\S+)\s+([\d.]+|unassigned)\s+\S+\s+\S+\s+(up|down|administratively down)\s+(up|down)", line)
            if m:
                brief_lines[m.group(1)] = m.groups()

        # `show interfaces` gives MAC + byte counters per interface, in
        # blocks separated by a blank line starting with the if name.
        blocks = re.split(r"\n(?=\S)", counters_output)
        counters_by_if: dict[str, dict] = {}
        for block in blocks:
            if_m = re.match(r"^(\S+)\s+is\s+(up|down|administratively down)", block)
            if not if_m:
                continue
            if_name = if_m.group(1)
            mac_m = re.search(r"address is\s+([0-9a-fA-F.]{14})", block)
            in_bytes_m = re.search(r"(\d+)\s+bytes.*?input", block)
            out_bytes_m = re.search(r"(\d+)\s+bytes.*?output", block)
            counters_by_if[if_name] = {
                "mac": mac_m.group(1) if mac_m else None,
                "rx_bytes": int(in_bytes_m.group(1)) if in_bytes_m else None,
                "tx_bytes": int(out_bytes_m.group(1)) if out_bytes_m else None,
            }

        for if_name, (name, ip, admin_line, oper_line) in brief_lines.items():
            admin_status = "disabled" if admin_line == "administratively down" else "enabled"
            oper_status = "up" if oper_line == "up" else "down"
            counters = counters_by_if.get(if_name, {})
            interfaces.append(Interface(
                device_id=self.device.device_id,
                if_name=if_name,
                status=oper_status,
                oper_status=oper_status,
                admin_status=admin_status,
                ip_address=None if ip == "unassigned" else ip,
                mac_address=counters.get("mac"),
                tx_bytes=counters.get("tx_bytes"),
                rx_bytes=counters.get("rx_bytes"),
            ))
        return interfaces

    def get_licenses(self) -> list:
        """Uses real Cisco Smart Licensing commands (`show license
        status` + `show license summary`), supported on IOS-XE 16.x/17.x
        for both routers and switches. Smart Licensing is subscription-
        based and this output doesn't expose a clean single expiry date
        per entitlement the way PAN-OS/FortiOS do -- expiry_date is
        left None here rather than guessed. Older IOS with classic
        Right-To-Use evaluation licensing uses a different command
        entirely (`show license right-to-use`) and isn't covered by
        this parser yet."""
        from app.models import License

        status_output = self._run("show license status")
        summary_output = self._run("show license summary")

        registered = "Status: REGISTERED" in status_output
        licenses = []
        # `show license summary` entitlement lines look like:
        #   network-advantage      (ISR_1100-4G:network-advantage)      1  IN USE
        for line in summary_output.splitlines():
            m = re.match(r"^\s*(\S[\w\-]*)\s+\(([^)]+)\)\s+(\d+)\s+(IN USE|NOT IN USE|OUT OF COMPLIANCE)", line)
            if not m:
                continue
            feature, entitlement_tag, count, status_text = m.groups()
            licenses.append(License(
                device_id=self.device.device_id,
                feature=feature,
                description=f"entitlement: {entitlement_tag}, registered: {registered}",
                expiry_date=None,  # Smart Licensing doesn't expose this cleanly here
                status="active" if status_text == "IN USE" else "unknown",
            ))
        return licenses

    def get_running_config(self) -> str:
        """Real `show running-config` output, straight from the CLI."""
        return self._run("show running-config")

    def get_neighbors(self) -> list[DiscoveredNeighbor]:
        """Parses `show cdp neighbors detail` for topology discovery.
        LLDP (`show lldp neighbors detail`) follows the same pattern
        if CDP is disabled -- swap the command if needed for your env."""
        output = self._run("show cdp neighbors detail")
        neighbors = []
        blocks = output.split("-------------------------")
        for block in blocks:
            hostname_m = re.search(r"Device ID:\s*(\S+)", block)
            local_if_m = re.search(r"Interface:\s*(\S+),", block)
            remote_if_m = re.search(r"Port ID \(outgoing port\):\s*(\S+)", block)
            ip_m = re.search(r"IP address:\s*([\d.]+)", block)
            if hostname_m and local_if_m and remote_if_m:
                neighbors.append(DiscoveredNeighbor(
                    device_id=self.device.device_id,
                    local_interface=local_if_m.group(1),
                    neighbor_hostname=hostname_m.group(1),
                    neighbor_interface=remote_if_m.group(1),
                    neighbor_mgmt_ip=ip_m.group(1) if ip_m else None,
                ))
        return neighbors

    def get_logs(self, filters: dict, time_range: tuple) -> list[LogEvent]:
        """IOS syslog is typically shipped off-box to a central syslog
        receiver rather than pulled on-demand -- `show logging` gives
        the local buffer, which is what's implemented here. Production
        deployments should also run a syslog receiver and feed those
        events into the same LogEvent store.

        Cisco routers/switches don't generate threat or URL logs
        (that's a firewall/UTM feature) -- requesting those log types
        here honestly returns nothing rather than fabricating data."""
        log_type = filters.get("log_type", "system")
        if log_type != "system":
            return []

        output = self._run("show logging | last 200")
        events = []
        for line in output.splitlines():
            m = re.match(r"^\*?(\w+\s+\d+\s+[\d:]+).*?%(\S+):\s*(.*)$", line)
            if not m:
                continue
            ts_raw, facility, message = m.groups()
            events.append(LogEvent(
                device_id=self.device.device_id,
                timestamp=datetime.utcnow(),  # IOS timestamps need NTP+year context to parse reliably
                severity="info",
                event_type=LogEventType.SYSTEM,
                raw_original=line,
            ))
        return events

    def health_check(self) -> HealthSnapshot:
        cpu_output = self._run("show processes cpu | include CPU utilization")
        mem_output = self._run("show memory statistics | include Processor")
        uptime_output = self._run("show version | include uptime is")

        cpu_m = re.search(r"five seconds:\s*(\d+)%", cpu_output)
        mem_m = re.search(r"Processor\s+\d+\s+(\d+)\s+(\d+)", mem_output)
        uptime_m = re.search(r"uptime is (.+)", uptime_output)

        mem_pct = None
        if mem_m:
            total, used = int(mem_m.group(1)), int(mem_m.group(2))
            mem_pct = round((used / total) * 100, 1) if total else None

        return HealthSnapshot(
            device_id=self.device.device_id,
            timestamp=datetime.utcnow(),
            cpu_pct=float(cpu_m.group(1)) if cpu_m else None,
            memory_pct=mem_pct,
            uptime_seconds=_parse_uptime(uptime_m.group(1)) if uptime_m else None,
        )

    def open_cli_session(self) -> CLISession:
        return self._cli_session_factory()


def _parse_uptime(text: str) -> Optional[int]:
    """'2 weeks, 3 days, 4 hours, 12 minutes' -> seconds"""
    units = {"week": 604800, "day": 86400, "hour": 3600, "minute": 60}
    total = 0
    for value, unit in re.findall(r"(\d+)\s+(week|day|hour|minute)", text):
        total += int(value) * units[unit]
    return total or None


class CiscoIOSRouterDriver(CiscoIOSDriverBase):
    def get_route(self, destination_ip: str) -> list[RouteEntry]:
        output = self._run(f"show ip route {destination_ip}")
        routes = []
        # Typical IOS/IOS-XE line: "  * 10.0.0.254, from 10.0.0.254, via GigabitEthernet1"
        m = re.search(r"\*\s*([\d.]+),.*?via\s+(\S+)", output)
        if m:
            next_hop, egress_if = m.groups()
            protocol = "connected"
            if re.search(r'Known via "ospf', output):
                protocol = "ospf"
            elif re.search(r'Known via "bgp', output):
                protocol = "bgp"
            elif re.search(r'Known via "static', output):
                protocol = "static"
            routes.append(RouteEntry(
                device_id=self.device.device_id,
                destination_subnet=destination_ip,
                next_hop=next_hop,
                egress_interface=egress_if.rstrip("."),
                protocol=protocol,
            ))
        return routes

    def get_sessions(self, src_ip=None, dst_ip=None) -> list:
        """Real flow/session data from Cisco's classic NetFlow cache
        (`show ip cache flow`) -- widely supported across IOS/IOS-XE
        even without a dedicated flow collector configured. This is
        the router-side equivalent of a firewall's session table: it
        lets the correlation engine confirm "did this flow actually
        transit this router" rather than only "is there a route for
        it." Ports and protocol in the raw output are hex, decoded
        here. NetFlow doesn't do application identification the way
        a firewall's App-ID/NGFW engine does, so `app` is left None --
        honestly absent, not guessed."""
        from app.models import Session

        output = self._run("show ip cache flow")
        sessions = []
        # Data rows look like:
        # SrcIf   SrcIPaddress   DstIf   DstIPaddress   Pr SrcP DstP  Pkts
        # Gi0/1   10.1.1.5       Gi0/2   157.240.1.1    06 0050 01BB    10
        for line in output.splitlines():
            m = re.match(
                r"^\S+\s+([\d.]+)\s+\S+\s+([\d.]+)\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+(\d+)",
                line,
            )
            if not m:
                continue
            flow_src, flow_dst, proto_hex, src_port_hex, dst_port_hex, pkts = m.groups()
            if src_ip and flow_src != src_ip:
                continue
            if dst_ip and flow_dst != dst_ip:
                continue
            proto_num = int(proto_hex, 16)
            sessions.append(Session(
                device_id=self.device.device_id,
                src_ip=flow_src, dst_ip=flow_dst,
                src_port=int(src_port_hex, 16), dst_port=int(dst_port_hex, 16),
                protocol=_PROTO_NUM_TO_NAME.get(proto_num, str(proto_num)),
                app=None,  # NetFlow has no App-ID equivalent
                state="active",
            ))
        return sessions


class CiscoIOSSwitchDriver(CiscoIOSDriverBase):
    def get_arp_mac_table(self) -> list[MacArpEntry]:
        mac_output = self._run("show mac address-table")
        arp_output = self._run("show ip arp")

        mac_by_addr: dict[str, tuple[int, str]] = {}
        for line in mac_output.splitlines():
            m = re.match(r"^\s*(\d+)\s+([0-9a-fA-F.]{14})\s+\S+\s+(\S+)", line)
            if m:
                vlan, mac, port = m.groups()
                mac_by_addr[mac.lower()] = (int(vlan), port)

        ip_by_mac: dict[str, str] = {}
        for line in arp_output.splitlines():
            m = re.match(r"^Internet\s+([\d.]+)\s+\S+\s+([0-9a-fA-F.]{14})", line)
            if m:
                ip, mac = m.groups()
                ip_by_mac[mac.lower()] = ip

        entries = []
        for mac, (vlan, port) in mac_by_addr.items():
            entries.append(MacArpEntry(
                device_id=self.device.device_id,
                mac_address=mac,
                ip_address=ip_by_mac.get(mac),
                vlan_id=vlan,
                interface=port,
            ))
        return entries
