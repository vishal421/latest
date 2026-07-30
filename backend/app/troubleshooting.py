"""Redesigned Troubleshooting engine.

Per the design brief, this is built on three "backbone" data sources
instead of a fresh live device call for every single step:

1. Traffic logs  -- already continuously collected into log_store
   (see log_store.py / the Logs page). Used to determine whether a
   flow actually reached a firewall, and whether it was allowed or
   denied.
2. Session logs  -- each device's live session/flow table (the same
   data the Logs page's Sessions tab and driver.get_sessions() already
   expose). Used as the router-side "did this flow transit here"
   confirmation, since routers don't produce per-flow traffic logs.
3. Config file   -- the latest downloaded ConfigBackup for each device
   (see config_backups.py / Devices → Actions → Pull/View Configuration),
   parsed by config_analysis.py for NAT rules and static routes.

Nothing here opens a fresh live connection to a device mid-trace --
if the data needed isn't already collected (no traffic logs yet, no
config backup pulled yet), the relevant step says so honestly instead
of falling back to a live query the person didn't ask for.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from app.models import Device, DeviceType, TroubleshootingStep, TroubleshootingResult
from app.drivers.factory import get_driver
from app.drivers.base import DriverNotSupported
from app.store import store
from app.config_analysis import parse_static_routes, parse_nat_rules, longest_prefix_match, find_nat_match
from app.scheduler import SESSION_RETENTION_MINUTES

_LOOKBACK_MINUTES = 30  # matches the 30-minute log retention window


def _latest_config_text(device_id: str) -> Optional[str]:
    backups = store.list_config_backups(device_id=device_id, limit=20)
    latest_success = next((b for b in backups if b.status == "success"), None)
    if not latest_success or not latest_success.backup_id:
        return None
    return store.get_config_backup_content(latest_success.backup_id)


def _traffic_log_step(device: Device, src_ip: str, dst_ip: str, protocol: Optional[str]) -> TroubleshootingStep:
    since = datetime.utcnow() - timedelta(minutes=_LOOKBACK_MINUTES)
    matches = store.search_logs(
        device_id=device.device_id, src_ip=src_ip, dst_ip=dst_ip,
        event_type="traffic", since=since, limit=20,
    )
    if not matches:
        return TroubleshootingStep(
            stage="firewall_traffic", device_id=device.device_id, status="fail",
            summary="Traffic never reached firewall.",
            source="traffic_log",
            detail={"lookback_minutes": _LOOKBACK_MINUTES},
        )
    latest = matches[0]
    action = (latest.action or "unknown").lower()
    passed = action in ("allow", "allowed")
    summary = f"Traffic log shows action={action}" + (f", rule '{latest.matched_rule}'" if latest.matched_rule else "")
    return TroubleshootingStep(
        stage="firewall_traffic", device_id=device.device_id,
        status="pass" if passed else "fail", summary=summary,
        source="traffic_log",
        detail={
            "action": action, "matched_rule": latest.matched_rule,
            "timestamp": latest.timestamp.isoformat(), "matching_logs": len(matches),
        },
    )


def _router_session_step(device: Device, src_ip: str, dst_ip: str) -> TroubleshootingStep:
    driver = get_driver(device)
    try:
        driver.connect()
        sessions = driver.get_sessions(src_ip=src_ip, dst_ip=dst_ip)
    except DriverNotSupported:
        return TroubleshootingStep(
            stage="router_log", device_id=device.device_id, status="fail",
            summary="No router log found.",
            source="session_log",
            detail={"reason": "This router's driver doesn't expose a session/flow table."},
        )
    except Exception as exc:  # noqa: BLE001 -- device unreachable, auth failure, etc: report, don't crash the trace
        return TroubleshootingStep(
            stage="router_log", device_id=device.device_id, status="fail",
            summary="No router log found.",
            source="session_log",
            detail={"reason": f"Could not query the router: {exc}"},
        )
    if not sessions:
        return TroubleshootingStep(
            stage="router_log", device_id=device.device_id, status="fail",
            summary="No router log found.",
            source="session_log",
            detail={},
        )
    return TroubleshootingStep(
        stage="router_log", device_id=device.device_id, status="pass",
        summary=f"Flow seen in the router's session/flow table ({len(sessions)} matching entr{'y' if len(sessions) == 1 else 'ies'}).",
        source="session_log",
        detail={"sessions_found": len(sessions)},
    )


def _firewall_session_history_step(device: Device, src_ip: str, dst_ip: str) -> TroubleshootingStep:
    since = datetime.utcnow() - timedelta(minutes=_LOOKBACK_MINUTES)
    matches = store.search_sessions(device_id=device.device_id, src_ip=src_ip, dst_ip=dst_ip, since=since, limit=20)
    if not matches:
        return TroubleshootingStep(
            stage="firewall_session_history", device_id=device.device_id, status="not_applicable",
            summary="No matching session found in the last 60 minutes of polled session history.",
            source="session_log", detail={"lookback_minutes": SESSION_RETENTION_MINUTES},
        )
    latest = matches[0]
    return TroubleshootingStep(
        stage="firewall_session_history", device_id=device.device_id, status="pass",
        summary=f"Session history shows {len(matches)} matching snapshot(s), most recently state={latest.state or 'unknown'}.",
        source="session_log",
        detail={"snapshots_found": len(matches), "latest_state": latest.state},
    )


def _nat_step(device: Device, src_ip: str, dst_ip: str) -> TroubleshootingStep:
    config_text = _latest_config_text(device.device_id)
    if config_text is None:
        return TroubleshootingStep(
            stage="nat", device_id=device.device_id, status="not_applicable",
            summary="No configuration backup available for NAT analysis -- pull one from Devices → Actions.",
            source="config_file", detail={},
        )
    nat_rules = parse_nat_rules(device.vendor, device.device_id, config_text)
    match = find_nat_match(nat_rules, src_ip, dst_ip)
    if match is None:
        return TroubleshootingStep(
            stage="nat", device_id=device.device_id, status="not_applicable",
            summary="No NAT Match.",
            source="config_file", detail={"nat_rules_checked": len(nat_rules)},
        )
    return TroubleshootingStep(
        stage="nat", device_id=device.device_id, status="pass",
        summary=f"NAT rule '{match.name}' ({match.nat_type}) applies -- translated to {match.translated_address}.",
        source="config_file",
        detail={"rule_name": match.name, "nat_type": match.nat_type, "translated_address": match.translated_address},
    )


def _routing_step(device: Device, dst_ip: str) -> TroubleshootingStep:
    config_text = _latest_config_text(device.device_id)
    if config_text is None:
        return TroubleshootingStep(
            stage="routing", device_id=device.device_id, status="not_applicable",
            summary="No configuration backup available for routing analysis -- pull one from Devices → Actions.",
            source="config_file", detail={},
        )
    routes = parse_static_routes(device.vendor, device.device_id, config_text)
    match = longest_prefix_match(routes, dst_ip)
    if match is None:
        return TroubleshootingStep(
            stage="routing", device_id=device.device_id, status="fail",
            summary="No matching route found in the downloaded configuration.",
            source="config_file", detail={"static_routes_checked": len(routes)},
        )
    is_default = match.destination_subnet in ("0.0.0.0/0",)
    summary = (
        f"Longest-prefix match: {match.destination_subnet} via {match.next_hop}"
        + (f" (egress {match.egress_interface})" if match.egress_interface else "")
        + (" -- default route" if is_default else "")
    )
    return TroubleshootingStep(
        stage="routing", device_id=device.device_id, status="pass", summary=summary,
        source="config_file",
        detail={
            "matched_subnet": match.destination_subnet, "next_hop": match.next_hop,
            "egress_interface": match.egress_interface, "is_default_route": is_default,
        },
    )


def _return_traffic_step(device: Device, src_ip: str, dst_ip: str) -> TroubleshootingStep:
    # Reverse direction: did the reply (dst_ip -> src_ip) show up in
    # this device's traffic logs.
    since = datetime.utcnow() - timedelta(minutes=_LOOKBACK_MINUTES)
    matches = store.search_logs(
        device_id=device.device_id, src_ip=dst_ip, dst_ip=src_ip,
        event_type="traffic", since=since, limit=10,
    )
    if not matches:
        return TroubleshootingStep(
            stage="return_traffic", device_id=device.device_id, status="fail",
            summary="No return traffic observed in logs.",
            source="traffic_log", detail={"lookback_minutes": _LOOKBACK_MINUTES},
        )
    latest = matches[0]
    action = (latest.action or "unknown").lower()
    return TroubleshootingStep(
        stage="return_traffic", device_id=device.device_id,
        status="pass" if action in ("allow", "allowed") else "fail",
        summary=f"Return traffic seen, action={action}.",
        source="traffic_log",
        detail={"action": action, "timestamp": latest.timestamp.isoformat()},
    )


def _select_devices(device_id: Optional[str]) -> list[Device]:
    if device_id:
        device = store.get_device(device_id)
        return [device] if device else []
    return store.list_devices()


def run_troubleshooting(src_ip: str, dst_ip: str, protocol: Optional[str] = None, device_id: Optional[str] = None) -> TroubleshootingResult:
    devices = _select_devices(device_id)
    routers = [d for d in devices if d.device_type == DeviceType.ROUTER]
    firewalls = [d for d in devices if d.device_type == DeviceType.FIREWALL]

    steps: list[TroubleshootingStep] = []

    # 1. Router stage -- session/flow-table confirmation.
    for router in routers:
        steps.append(_router_session_step(router, src_ip, dst_ip))

    # 2. Firewall stage -- did traffic reach it, allow/deny, which rule,
    # plus what the polled session history separately shows.
    for fw in firewalls:
        steps.append(_traffic_log_step(fw, src_ip, dst_ip, protocol))
        steps.append(_firewall_session_history_step(fw, src_ip, dst_ip))

    # 3 & 4. NAT and routing analysis, config-file-backed, for every
    # device that has one, regardless of whether the traffic-log step
    # passed -- useful even when troubleshooting a route that's never
    # been used yet.
    for device in firewalls + routers:
        steps.append(_nat_step(device, src_ip, dst_ip))
        steps.append(_routing_step(device, dst_ip))

    # 5. Return traffic, firewalls only (routers don't log per-flow traffic).
    for fw in firewalls:
        steps.append(_return_traffic_step(fw, src_ip, dst_ip))

    identity = store.resolve_identity(src_ip)
    who = f"{identity.username} ({src_ip})" if identity else src_ip

    if not devices:
        verdict = "No devices onboarded yet -- nothing to check." if not device_id else "Device not found."
    else:
        blocking = next((s for s in steps if s.status == "fail" and s.stage in ("firewall_traffic", "routing", "router_log")), None)
        if blocking:
            verdict = f"Blocked at {blocking.stage.replace('_', ' ')} on {blocking.device_id} for {who}: {blocking.summary}"
        else:
            verdict = f"No blocking step found for {who} across every checked device -- traffic, routing, and NAT all check out against the collected data."

    result = TroubleshootingResult(
        src_ip=src_ip, dst_ip=dst_ip, protocol=protocol, device_id=device_id,
        steps=steps, verdict=verdict,
    )
    return result
