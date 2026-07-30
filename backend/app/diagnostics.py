"""
Automated traffic-flow diagnostics engine.

Phase 4: uses topology-based path selection (app/path_selection.py)
when there's enough wired topology data to trust it -- walking the
actual switch -> router -> firewall path instead of checking every
onboarded device of each type. Falls back to the Phase 2 behavior
(check every switch/router/firewall) when topology data isn't there
yet, so this stays useful before anything's been wired up in the
Topology tab.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models import Device, DeviceType, HopResult, DiagnosticsResult
from app.drivers.factory import get_driver
from app.drivers.base import DriverNotSupported
from app.store import store
from app.path_selection import find_path_devices


def _switch_hop(device: Device, src_ip: str) -> HopResult:
    driver = get_driver(device)
    driver.connect()
    entries = driver.get_arp_mac_table()
    match = next((e for e in entries if e.ip_address == src_ip), None)

    if match is None:
        return HopResult(
            device_id=device.device_id, hop_type="switch", passed=False,
            reason=f"Source {src_ip} not found in ARP/MAC table -- host may be offline or on a different switch",
            detail={},
        )
    return HopResult(
        device_id=device.device_id, hop_type="switch", passed=True,
        reason=f"Source {src_ip} seen on interface {match.interface} (VLAN {match.vlan_id})",
        detail={"interface": match.interface, "vlan_id": match.vlan_id, "mac_address": match.mac_address},
    )


def _router_hop(device: Device, src_ip: str, dst_ip: str) -> HopResult:
    driver = get_driver(device)
    driver.connect()
    routes = driver.get_route(dst_ip)

    # Session/flow confirmation (e.g. Cisco NetFlow cache) is optional --
    # not every router driver implements it. When it's there, it lets
    # the verdict say "confirmed in the flow cache," not just "a route
    # exists" -- a real route doesn't prove traffic actually transited
    # this router, a matching flow entry does.
    flow_confirmed = None
    try:
        flows = driver.get_sessions(src_ip=src_ip, dst_ip=dst_ip)
        flow_confirmed = len(flows) > 0
    except DriverNotSupported:
        pass

    if not routes:
        return HopResult(
            device_id=device.device_id, hop_type="router", passed=False,
            reason=f"No route to {dst_ip} found",
            detail={"flow_confirmed": flow_confirmed},
        )
    route = routes[0]
    reason = f"Route to {dst_ip} via {route.next_hop} ({route.protocol})"
    if flow_confirmed is True:
        reason += " -- confirmed in the flow/session cache"
    elif flow_confirmed is False:
        reason += " -- route exists but no matching flow seen yet"
    return HopResult(
        device_id=device.device_id, hop_type="router", passed=True,
        reason=reason,
        detail={
            "next_hop": route.next_hop, "protocol": route.protocol,
            "egress_interface": route.egress_interface, "flow_confirmed": flow_confirmed,
        },
    )


def _firewall_hop(device: Device, src_ip: str, dst_ip: str, port: int, protocol: str) -> HopResult:
    driver = get_driver(device)
    driver.connect()

    rule = driver.test_policy_match(src_ip, dst_ip, port, protocol)
    sessions = driver.get_sessions(src_ip=src_ip, dst_ip=dst_ip)
    recent_logs = driver.get_logs(
        {"src_ip": src_ip, "dst_ip": dst_ip},
        (datetime.utcnow() - timedelta(minutes=15), datetime.utcnow()),
    )

    if rule is None:
        return HopResult(
            device_id=device.device_id, hop_type="firewall", passed=False,
            reason="No matching policy rule found for this flow",
            detail={"sessions_found": len(sessions), "recent_logs": len(recent_logs)},
        )

    passed = rule.action.lower() in ("allow", "accept")
    reason = f"Policy '{rule.name}' (rule {rule.rule_id}) would {rule.action.upper()} this flow"
    return HopResult(
        device_id=device.device_id, hop_type="firewall", passed=passed, reason=reason,
        detail={
            "rule_id": rule.rule_id, "rule_name": rule.name, "action": rule.action,
            "sessions_found": len(sessions), "recent_matching_logs": len(recent_logs),
        },
    )


def _run_hop(device: Device, src_ip: str, dst_ip: str, port: int, protocol: str) -> HopResult | None:
    if device.device_type == DeviceType.SWITCH:
        return _switch_hop(device, src_ip)
    if device.device_type == DeviceType.ROUTER:
        return _router_hop(device, src_ip, dst_ip)
    if device.device_type == DeviceType.FIREWALL:
        return _firewall_hop(device, src_ip, dst_ip, port, protocol)
    return None


def run_diagnostics(src_ip: str, dst_ip: str, port: int, protocol: str) -> DiagnosticsResult:
    path_devices = find_path_devices(src_ip, dst_ip)

    if path_devices is not None:
        path_source = "topology"
        ordered_devices = path_devices
    else:
        path_source = "fallback-all-devices"
        devices = store.list_devices()
        ordered_devices = (
            [d for d in devices if d.device_type == DeviceType.SWITCH]
            + [d for d in devices if d.device_type == DeviceType.ROUTER]
            + [d for d in devices if d.device_type == DeviceType.FIREWALL]
        )

    hops: list[HopResult] = []
    for device in ordered_devices:
        hop = _run_hop(device, src_ip, dst_ip, port, protocol)
        if hop:
            hops.append(hop)

    # Identity-aware correlation: if this IP is a known user binding
    # (see app/api/identities.py), the verdict names the person, not
    # just the address -- most tools stop at "10.1.1.5", which breaks
    # the moment DHCP reassigns it.
    identity = store.resolve_identity(src_ip)
    who = f"{identity.username} ({src_ip})" if identity else src_ip

    if not hops:
        verdict = "No devices onboarded yet -- nothing to check."
    else:
        failed = [h for h in hops if not h.passed]
        if failed:
            first = failed[0]
            verdict = f"Blocked at {first.hop_type} ({first.device_id}) for {who}: {first.reason}"
        else:
            verdict = f"Traffic passes every checked hop for {who} -- no blocking device found."

    result = DiagnosticsResult(
        src_ip=src_ip, dst_ip=dst_ip, port=port, protocol=protocol,
        hops=hops, verdict=verdict, path_source=path_source,
    )
    store.add_diagnostics_result(result)
    return result
