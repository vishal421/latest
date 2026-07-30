"""
Fortigate FortiOS driver.

Uses the FortiOS REST API (https://<mgmt_ip>/api/v2/...) with an API
token for monitor/cmdb calls, and SSH for the interactive CLI session
and for the one diagnostic command that has no clean REST equivalent
(policy lookup). Exact endpoint paths/fields should be verified
against your lab device's FortiOS version -- they shift slightly
across major releases (6.x vs 7.x).

`http_client` is injected so tests can substitute a fake transport
instead of hitting a real device.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import requests

from app.models import (
    Device, Interface, Session, PolicyRule, LogEvent, LogEventType,
    HealthSnapshot, License,
)
from app.drivers.base import DeviceDriver, CLISession, SSHShellSession

# FortiOS splits log data across separate disk-log endpoints per
# category, unlike PAN-OS's single endpoint. "threat" maps to the IPS
# attack log as the primary threat feed -- a fuller implementation
# would also merge virus/app-ctrl/waf logs, left as a follow-up.
_FORTIOS_LOG_ENDPOINTS = {
    "traffic": "log/disk/traffic/forward",
    "threat": "log/disk/ips",
    "url": "log/disk/webfilter/webfilter",
    "system": "log/disk/event/system",
}
_FORTIOS_LOG_TYPE_MAP = {
    "traffic": LogEventType.TRAFFIC,
    "threat": LogEventType.THREAT,
    "url": LogEventType.URL,
    "system": LogEventType.SYSTEM,
}


class FortigateCLISession(SSHShellSession):
    """FortiOS's CLI drops straight into a usable prompt on connect --
    no vendor-specific setup needed, so this is a plain alias for the
    shared SSH session."""


class FortigateDriver(DeviceDriver):
    def __init__(self, device: Device, credential: dict, http_client=None):
        super().__init__(device, credential)
        self._http = http_client or requests
        self._token = credential.get("api_key")

    @property
    def _base_url(self) -> str:
        return f"https://{self.device.mgmt_ip}/api/v2"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def connect(self) -> None:
        resp = self._http.get(
            f"{self._base_url}/monitor/system/status",
            headers=self._headers(), verify=False, timeout=10,
        )
        resp.raise_for_status()

    def get_facts(self) -> Device:
        resp = self._http.get(
            f"{self._base_url}/monitor/system/status",
            headers=self._headers(), verify=False, timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("results", {})
        self.device.model = data.get("model_name", self.device.model)
        self.device.os_version = data.get("version", self.device.os_version)
        self.device.serial_number = data.get("serial", self.device.serial_number)
        self.device.hostname = data.get("hostname", self.device.hostname)
        self.device.last_seen = datetime.utcnow()
        return self.device

    def get_interfaces(self) -> list[Interface]:
        resp = self._http.get(
            f"{self._base_url}/monitor/system/interface",
            headers=self._headers(), verify=False, timeout=10,
        )
        resp.raise_for_status()
        interfaces = []
        for name, entry in resp.json().get("results", {}).items():
            oper_up = bool(entry.get("link"))
            # FortiOS's admin status ("status": "up"/"down" -- whether the
            # interface is administratively enabled) is a separate field
            # from "link" (physical/oper state).
            admin_raw = entry.get("status")
            admin_status = admin_raw if admin_raw in ("up", "down") else "unknown"
            interfaces.append(Interface(
                device_id=self.device.device_id,
                if_name=name,
                status="up" if oper_up else "down",
                oper_status="up" if oper_up else "down",
                admin_status="enabled" if admin_status == "up" else ("disabled" if admin_status == "down" else "unknown"),
                ip_address=entry.get("ip"),
                mac_address=entry.get("mac") or entry.get("mac_address"),
                tx_bytes=entry.get("tx_bytes"),
                rx_bytes=entry.get("rx_bytes"),
            ))
        return interfaces

    def get_sessions(self, src_ip: Optional[str] = None, dst_ip: Optional[str] = None) -> list[Session]:
        params = {}
        if src_ip:
            params["filter"] = f"src=={src_ip}"
        resp = self._http.get(
            f"{self._base_url}/monitor/firewall/session",
            headers=self._headers(), params=params, verify=False, timeout=15,
        )
        resp.raise_for_status()
        sessions = []
        for entry in resp.json().get("results", []):
            if dst_ip and entry.get("dst") != dst_ip:
                continue
            sessions.append(Session(
                device_id=self.device.device_id,
                src_ip=entry.get("src", ""),
                dst_ip=entry.get("dst", ""),
                src_port=entry.get("src_port"),
                dst_port=entry.get("dst_port"),
                protocol=str(entry.get("proto", "")),
                app=entry.get("app"),
                state=entry.get("state", "unknown"),
            ))
        return sessions

    def test_policy_match(self, src_ip: str, dst_ip: str, port: int, proto: str) -> Optional[PolicyRule]:
        """FortiOS doesn't expose as clean a REST policy-lookup as PAN-OS's
        test-security-policy-match, so this shells out to the CLI
        diagnostic (`diagnose firewall iprope lookup`) and parses the
        matched policy ID out of the text response. Verify the exact
        output format against your FortiOS version."""
        session = self.open_cli_session()
        try:
            proto_num = {"tcp": 6, "udp": 17}.get(proto.lower(), 6)
            cmd = f"diagnose firewall iprope lookup {src_ip} {dst_ip} {port} {proto_num} 0"
            output = session.send_command(cmd)
        finally:
            session.close()

        import re
        m = re.search(r"policy_id[=:]\s*(\d+)", output)
        if not m:
            return None
        return PolicyRule(
            device_id=self.device.device_id,
            rule_id=m.group(1),
            name=f"policy-{m.group(1)}",
            action="allow" if "action=accept" in output else "deny",
        )

    def get_policy_rules(self) -> list[PolicyRule]:
        resp = self._http.get(
            f"{self._base_url}/cmdb/firewall/policy",
            headers=self._headers(), verify=False, timeout=15,
        )
        resp.raise_for_status()
        rules = []
        for entry in resp.json().get("results", []):
            rules.append(PolicyRule(
                device_id=self.device.device_id,
                rule_id=str(entry.get("policyid", "")),
                name=entry.get("name", ""),
                action=entry.get("action", "unknown"),
                source=str(entry.get("srcaddr", "any")),
                destination=str(entry.get("dstaddr", "any")),
            ))
        return rules

    def get_logs(self, filters: dict, time_range: tuple) -> list[LogEvent]:
        """FortiOS splits log types across different disk-log endpoints
        (unlike PAN-OS's single endpoint with a log-type parameter).
        Exact field names per log type (especially threat/url) vary by
        FortiOS version -- verify against your instance; this parses
        the commonly-seen field names as of FortiOS 7.x."""
        log_type = filters.get("log_type", "traffic")
        endpoint = _FORTIOS_LOG_ENDPOINTS.get(log_type, _FORTIOS_LOG_ENDPOINTS["traffic"])

        params = {"start": 0, "rows": 200}
        if filters.get("src_ip"):
            params["filter"] = f"srcip=={filters['src_ip']}"
        resp = self._http.get(
            f"{self._base_url}/{endpoint}",
            headers=self._headers(), params=params, verify=False, timeout=20,
        )
        resp.raise_for_status()
        events = []
        for entry in resp.json().get("results", []):
            events.append(LogEvent(
                device_id=self.device.device_id,
                timestamp=_safe_dt(entry.get("date"), entry.get("time")),
                severity=entry.get("level", "info"),
                event_type=_FORTIOS_LOG_TYPE_MAP.get(log_type, LogEventType.TRAFFIC),
                src_ip=entry.get("srcip"),
                dst_ip=entry.get("dstip"),
                action=entry.get("action"),
                raw_original=str(entry),
                threat_name=(entry.get("attack") or entry.get("msg")) if log_type == "threat" else None,
                url=entry.get("url") if log_type == "url" else None,
                category=(entry.get("catdesc") or entry.get("category")) if log_type == "url" else None,
                user=entry.get("user") if log_type in ("url", "traffic") else None,
                app=(entry.get("app") or entry.get("service")) if log_type in ("traffic", "threat") else None,
                # FortiOS traffic logs carry sent/received byte counts
                # separately and the matched policy as policyname/id.
                bytes_total=_sum_bytes(entry) if log_type == "traffic" else None,
                matched_rule=str(entry.get("policyname") or entry.get("policyid") or "") or None if log_type == "traffic" else None,
            ))
        return events

    def health_check(self) -> HealthSnapshot:
        resp = self._http.get(
            f"{self._base_url}/monitor/system/resource/usage",
            headers=self._headers(), verify=False, timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("results", {})
        cpu_series = data.get("cpu", {}).get("current", [{}])
        mem_series = data.get("mem", {}).get("current", [{}])
        return HealthSnapshot(
            device_id=self.device.device_id,
            timestamp=datetime.utcnow(),
            cpu_pct=cpu_series[0].get("value") if cpu_series else None,
            memory_pct=mem_series[0].get("value") if mem_series else None,
        )

    def get_licenses(self) -> list:
        """Uses FortiOS's real `/monitor/license/status` endpoint.
        Unlike PAN-OS's license op-command, FortiOS's response shape
        here isn't a flat list -- it's a dict of license bundles
        (forticare, fortiguard_av, fortiguard_ips, etc.), each with its
        own status/expiry fields, and the exact field names shift
        across FortiOS versions. This parses generically (any nested
        dict with an expiry-like or validity-like key becomes a
        License entry) -- verify the resulting feature names/dates
        against your actual FortiOS version before trusting them."""
        resp = self._http.get(
            f"{self._base_url}/monitor/license/status",
            headers=self._headers(), verify=False, timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", {})
        licenses = []
        for key, value in results.items():
            if not isinstance(value, dict):
                continue
            expiry_raw = value.get("expiry_date") or value.get("expires") or value.get("expiration_date")
            is_valid = value.get("is_valid")
            status = "unknown"
            if is_valid is True:
                status = "active"
            elif is_valid is False:
                status = "expired"
            licenses.append(License(
                device_id=self.device.device_id,
                feature=key,
                description=str(value.get("desc", "")) if value.get("desc") else "",
                expiry_date=_parse_fortios_date(expiry_raw),
                status=status,
            ))
        return licenses

    def get_running_config(self) -> str:
        """Uses FortiOS's real `/monitor/system/config/backup` endpoint,
        which returns the full config as plain text (the same format
        the FortiGate GUI's "Backup Configuration" download produces)."""
        resp = self._http.get(
            f"{self._base_url}/monitor/system/config/backup",
            headers=self._headers(), params={"scope": "global"}, verify=False, timeout=30,
        )
        resp.raise_for_status()
        return resp.text

    def open_cli_session(self) -> CLISession:
        return FortigateCLISession(
            self.device.mgmt_ip,
            self._credential["username"],
            self._credential["password"],
        )


def _safe_dt(date_str, time_str):
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return datetime.utcnow()


def _sum_bytes(entry: dict):
    """FortiOS traffic logs report sent/received bytes separately
    (sentbyte/rcvdbyte) rather than one combined field like PAN-OS --
    sum them for a comparable total, or None if neither is present."""
    sent = entry.get("sentbyte")
    rcvd = entry.get("rcvdbyte")
    if sent is None and rcvd is None:
        return None
    return int(sent or 0) + int(rcvd or 0)


def _parse_fortios_date(raw):
    """FortiOS license expiry has been seen as either an epoch integer
    or an ISO-ish date string depending on version/endpoint -- try
    both rather than assuming one. Returns None (no expiry data / a
    perpetual license) if neither parses, rather than guessing."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.utcfromtimestamp(raw)
        except (ValueError, OSError):
            return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None
