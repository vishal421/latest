"""
Palo Alto PAN-OS driver.

Uses the PAN-OS XML API (https://<mgmt_ip>/api/) for op-commands,
config retrieval, and log queries, and SSH for the interactive CLI
session. Real PAN-OS devices vary slightly in XML schema between
major releases -- field paths here target 10.x/11.x and should be
verified against your actual lab device firmware.

`http_client` is injected so tests can substitute a fake transport
instead of hitting a real device.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

import requests

from app.models import (
    Device, Vendor, DeviceType, Interface, Session, PolicyRule,
    LogEvent, LogEventType, HealthSnapshot, License,
)
from app.drivers.base import DeviceDriver, CLISession, SSHShellSession, DriverNotSupported

# PAN-OS's real log-type query values -> our normalized LogEventType.
_PANOS_LOG_TYPE_MAP = {
    "traffic": LogEventType.TRAFFIC,
    "threat": LogEventType.THREAT,
    "url": LogEventType.URL,
    "system": LogEventType.SYSTEM,
}


class PaloAltoCLISession(SSHShellSession):
    """PAN-OS's operational CLI drops straight into a usable prompt on
    connect -- no vendor-specific setup (like Cisco's paging disable)
    needed, so this is a plain alias for the shared SSH session."""


class PaloAltoDriver(DeviceDriver):
    def __init__(self, device: Device, credential: dict, http_client=None):
        super().__init__(device, credential)
        self._http = http_client or requests
        self._api_key: Optional[str] = None

    @property
    def _base_url(self) -> str:
        return f"https://{self.device.mgmt_ip}/api/"

    def connect(self) -> None:
        """Exchange username/password for an API key, per PAN-OS convention."""
        resp = self._http.get(
            self._base_url,
            params={
                "type": "keygen",
                "user": self._credential["username"],
                "password": self._credential["password"],
            },
            verify=False,
            timeout=10,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        key_el = root.find(".//key")
        if key_el is None:
            raise ConnectionError("PAN-OS keygen failed -- check credentials")
        self._api_key = key_el.text

    def _op(self, cmd_xml: str) -> ET.Element:
        if not self._api_key:
            self.connect()
        resp = self._http.get(
            self._base_url,
            params={"type": "op", "cmd": cmd_xml, "key": self._api_key},
            verify=False,
            timeout=15,
        )
        resp.raise_for_status()
        return ET.fromstring(resp.text)

    def get_facts(self) -> Device:
        root = self._op("<show><system><info></info></system></show>")
        sysinfo = root.find(".//system")
        self.device.model = sysinfo.findtext("model", default=self.device.model)
        self.device.os_version = sysinfo.findtext("sw-version", default=self.device.os_version)
        self.device.serial_number = sysinfo.findtext("serial", default=self.device.serial_number)
        self.device.hostname = sysinfo.findtext("hostname", default=self.device.hostname)
        self.device.last_seen = datetime.utcnow()
        return self.device

    def get_interfaces(self) -> list[Interface]:
        """`show interface all` returns two sections: <ifnet> (logical/
        sub-interfaces -- name, zone, IP) and <hw> (physical interfaces
        only -- link state, MAC, speed/duplex). A sub-interface like
        ethernet1/1.100 gets its own <ifnet> entry but has no MAC of its
        own -- it shares its parent physical interface's -- so the <hw>
        lookup is checked by full name first, then by the physical
        portion before the dot.

        Byte counters aren't in this op-command's response at all; they
        come from the separate `show counter interface all` call in
        `_get_interface_counters()`, merged in by interface name below.
        """
        root = self._op("<show><interface>all</interface></show>")

        hw_by_name: dict[str, ET.Element] = {}
        for hw in root.findall(".//hw/entry"):
            name = hw.findtext("name")
            if name:
                hw_by_name[name] = hw

        counters_by_name = self._get_interface_counters()

        interfaces = []
        for entry in root.findall(".//ifnet/entry"):
            name = entry.findtext("name", default="unknown")
            physical_name = name.split(".")[0]  # ethernet1/1.100 -> ethernet1/1
            hw = hw_by_name.get(name)
            if hw is None:
                hw = hw_by_name.get(physical_name)

            oper_up = entry.findtext("state") == "up" or (hw is not None and hw.findtext("state") == "up")

            # PAN-OS's op-command output has no direct administratively-
            # enabled flag; a physical interface that's been `set
            # deviceconfig ... disabled yes` in config simply doesn't
            # appear under <hw> at all. Treating "no <hw> entry for a
            # physical interface" as disabled is a reasonable best-effort
            # read of that gap, not a guarantee -- verify against your
            # PAN-OS version if this matters operationally. Sub-interfaces
            # have no independent admin-disable of their own in PAN-OS,
            # so they're left "unknown" rather than inheriting the
            # parent's state incorrectly.
            if physical_name == name:
                admin_status = "enabled" if hw is not None else "disabled"
            else:
                admin_status = "unknown"

            tx_bytes, rx_bytes = counters_by_name.get(name, (None, None))

            interfaces.append(Interface(
                device_id=self.device.device_id,
                if_name=name,
                status="up" if oper_up else "down",
                oper_status="up" if oper_up else "down",
                admin_status=admin_status,
                ip_address=entry.findtext("ip"),
                mac_address=hw.findtext("mac") if hw is not None else None,
                tx_bytes=tx_bytes,
                rx_bytes=rx_bytes,
            ))
        return interfaces

    def _get_interface_counters(self) -> dict[str, tuple[Optional[int], Optional[int]]]:
        """`show counter interface all` -- PAN-OS's real hardware byte
        counters, keyed by interface name. `obytes`/`ibytes` are PAN-OS's
        own field names (output/Tx and input/Rx respectively on the
        physical interface).

        Returns an empty dict rather than raising if a device/version
        doesn't support the bulk `all` form, or the call otherwise fails
        (permissions, transient error) -- interface listing itself
        should still work even when live counters can't be fetched, the
        same "degrade to None, don't fabricate" pattern used elsewhere
        in this driver (see get_licenses' expiry handling).
        """
        try:
            root = self._op("<show><counter><interface>all</interface></counter></show>")
        except Exception:
            return {}
        counters: dict[str, tuple[Optional[int], Optional[int]]] = {}
        for entry in root.findall(".//ifnet/entry"):
            name = entry.findtext("name")
            if not name:
                continue
            counters[name] = (_safe_int(entry.findtext("obytes")), _safe_int(entry.findtext("ibytes")))
        return counters

    def get_sessions(self, src_ip: Optional[str] = None, dst_ip: Optional[str] = None) -> list[Session]:
        filter_xml = ""
        if src_ip:
            filter_xml += f"<source>{src_ip}</source>"
        if dst_ip:
            filter_xml += f"<destination>{dst_ip}</destination>"
        root = self._op(f"<show><session><all><filter>{filter_xml}</filter></all></session></show>")
        sessions = []
        for entry in root.findall(".//entry"):
            sessions.append(Session(
                device_id=self.device.device_id,
                src_ip=entry.findtext("source", default=""),
                dst_ip=entry.findtext("dst", default=""),
                src_port=_safe_int(entry.findtext("sport")),
                dst_port=_safe_int(entry.findtext("dport")),
                protocol=entry.findtext("proto", default=""),
                app=entry.findtext("application"),
                state=entry.findtext("state", default="unknown"),
            ))
        return sessions

    def test_policy_match(self, src_ip: str, dst_ip: str, port: int, proto: str) -> Optional[PolicyRule]:
        """Uses PAN-OS's native `test security-policy-match` op-command --
        this is the real, built-in policy simulation the design doc refers to."""
        proto_num = {"tcp": 6, "udp": 17}.get(proto.lower(), proto)
        cmd = (
            "<test><security-policy-match>"
            f"<source>{src_ip}</source><destination>{dst_ip}</destination>"
            f"<destination-port>{port}</destination-port><protocol>{proto_num}</protocol>"
            "</security-policy-match></test>"
        )
        root = self._op(cmd)
        rule_entry = root.find(".//rules/entry")
        if rule_entry is None:
            return None
        return PolicyRule(
            device_id=self.device.device_id,
            rule_id=rule_entry.get("name", "unknown"),
            name=rule_entry.get("name", "unknown"),
            action=rule_entry.findtext("action", default="unknown"),
        )

    def get_policy_rules(self) -> list[PolicyRule]:
        root = self._op("<show><running><security-policy></security-policy></running></show>")
        rules = []
        for entry in root.findall(".//rules/entry"):
            rules.append(PolicyRule(
                device_id=self.device.device_id,
                rule_id=entry.get("name", ""),
                name=entry.get("name", ""),
                action=entry.findtext("action", default="unknown"),
                source=entry.findtext("source/member", default="any"),
                destination=entry.findtext("destination/member", default="any"),
            ))
        return rules

    def get_logs(self, filters: dict, time_range: tuple) -> list[LogEvent]:
        """Two-step PAN-OS log query: submit job, then poll for results.
        Simplified here to a single synchronous call for clarity --
        production code should poll the job-id until status=FIN.

        `filters["log_type"]` selects which of PAN-OS's real log
        categories to query -- traffic, threat, url, or system (all
        real PAN-OS log-type values, same API shape, different field
        sets per type)."""
        log_type = filters.get("log_type", "traffic")
        query_parts = []
        if filters.get("src_ip"):
            query_parts.append(f"(addr.src in {filters['src_ip']})")
        if filters.get("dst_ip"):
            query_parts.append(f"(addr.dst in {filters['dst_ip']})")
        query = " and ".join(query_parts) or "all"

        resp = self._http.get(
            self._base_url,
            params={
                "type": "log", "log-type": log_type, "query": query,
                "key": self._api_key,
            },
            verify=False, timeout=20,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        events = []
        for entry in root.findall(".//logs/entry"):
            events.append(LogEvent(
                device_id=self.device.device_id,
                timestamp=_safe_dt(entry.findtext("receive_time")),
                severity=entry.findtext("severity", default="info"),
                event_type=_PANOS_LOG_TYPE_MAP.get(log_type, LogEventType.TRAFFIC),
                src_ip=entry.findtext("src"),
                dst_ip=entry.findtext("dst"),
                action=entry.findtext("action"),
                raw_original=ET.tostring(entry, encoding="unicode"),
                # threat logs: PAN-OS calls the signature name "threatid"
                threat_name=entry.findtext("threatid") if log_type == "threat" else None,
                # url logs: PAN-OS field is literally "url", category is "category"
                url=entry.findtext("url") if log_type == "url" else None,
                category=entry.findtext("category") if log_type == "url" else None,
                user=entry.findtext("srcuser") if log_type in ("url", "traffic") else None,
                app=entry.findtext("app") if log_type in ("traffic", "threat") else None,
                # PAN-OS traffic logs carry the real byte count and the
                # matched security-rule name directly on the entry.
                bytes_total=_safe_int(entry.findtext("bytes")) if log_type == "traffic" else None,
                matched_rule=entry.findtext("rule") if log_type == "traffic" else None,
            ))
        return events

    def health_check(self) -> HealthSnapshot:
        root = self._op("<show><system><resources></resources></system></show>")
        # PAN-OS wraps this op-command's raw `top`-style text directly in
        # <result> -- <resources> is only the request tag, it never
        # appears in the response, so looking for it here always
        # matched nothing and left cpu/memory permanently blank.
        raw = root.findtext(".//result", default="")
        return HealthSnapshot(
            device_id=self.device.device_id,
            timestamp=datetime.utcnow(),
            cpu_pct=_extract_cpu(raw),
            memory_pct=_extract_mem(raw),
        )

    def get_licenses(self) -> list:
        """Uses PAN-OS's real `request license info` op-command.
        Response nesting (whether entries sit under <licenses> or
        directly under <result>) varies slightly by PAN-OS version --
        searching `.//entry` handles either."""
        root = self._op("<request><license><info></info></license></request>")
        licenses = []
        for entry in root.findall(".//entry"):
            expires_raw = entry.findtext("expires")
            expired_flag = entry.findtext("expired", default="no")
            licenses.append(License(
                device_id=self.device.device_id,
                feature=entry.findtext("feature", default="unknown"),
                description=entry.findtext("description", default=""),
                expiry_date=_parse_panos_date(expires_raw),
                status="expired" if expired_flag == "yes" else "active",
            ))
        return licenses

    def get_running_config(self) -> str:
        """Uses PAN-OS's real `show config running` op-command, which
        returns the full running config as XML text."""
        root = self._op("<show><config><running></running></config></show>")
        config_el = root.find(".//config")
        if config_el is None:
            return ET.tostring(root, encoding="unicode")
        return ET.tostring(config_el, encoding="unicode")

    def open_cli_session(self) -> CLISession:
        return PaloAltoCLISession(
            self.device.mgmt_ip,
            self._credential["username"],
            self._credential["password"],
        )


def _safe_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_dt(v):
    try:
        return datetime.strptime(v, "%Y/%m/%d %H:%M:%S")
    except (TypeError, ValueError):
        return datetime.utcnow()


def _extract_cpu(raw: str) -> Optional[float]:
    import re
    m = re.search(r"Cpu\(s\):\s*([\d.]+)%?\s*us", raw)
    return float(m.group(1)) if m else None


def _extract_mem(raw: str) -> Optional[float]:
    import re
    m = re.search(r"KiB Mem.*?(\d+\.?\d*)%", raw)
    return float(m.group(1)) if m else None


def _parse_panos_date(raw: Optional[str]):
    """PAN-OS license dates look like 'January 01, 2027'. Returns None
    for missing/unparseable values (e.g. perpetual licenses with no
    expiry) rather than guessing -- a real absence, not an error."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%B %d, %Y")
    except ValueError:
        return None
