"""
Topology-based path selection.

Phase 2/3's diagnostics engine checked every onboarded switch/router/
firewall, which is fine for a single-site lab but wasteful (and
occasionally misleading) once there's real topology data to use
instead. This walks the actual wired graph: find which switch the
source IP is actually connected to, then follow links from there until
a firewall is reached (or the graph runs out).

Falls back to `None` (caller then falls back to "check everything") in
two cases: no topology links exist yet, or the source IP wasn't found
on any onboarded switch. Both are common in early testing (nothing
wired up yet) and shouldn't break diagnostics -- they should just make
it less precise, which is what the fallback does.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from app.models import Device, DeviceType
from app.drivers.factory import get_driver
from app.store import store
from app.topology import topology_store


def _find_entry_switch(src_ip: str) -> Optional[Device]:
    for sw in store.list_devices():
        if sw.device_type != DeviceType.SWITCH:
            continue
        try:
            driver = get_driver(sw)
            driver.connect()
            entries = driver.get_arp_mac_table()
        except Exception:
            continue
        if any(e.ip_address == src_ip for e in entries):
            return sw
    return None


def find_path_devices(src_ip: str, dst_ip: str) -> Optional[list[Device]]:
    """Returns an ordered list of Devices to check along the real path,
    or None to signal the caller should fall back to checking every
    onboarded device of each type."""
    links = topology_store.list_links()
    if not links:
        return None

    entry_switch = _find_entry_switch(src_ip)
    if entry_switch is None:
        return None

    adjacency: dict[str, list[str]] = defaultdict(list)
    for link in links:
        adjacency[link.device_a].append(link.device_b)
        adjacency[link.device_b].append(link.device_a)

    visited = {entry_switch.device_id}
    ordered_ids = [entry_switch.device_id]
    current = entry_switch.device_id

    # Simple walk along the graph -- correct for the common chain
    # topology (switch -> router -> firewall) this design targets; for
    # a branching graph with multiple routers/firewalls it's a
    # heuristic (first unvisited neighbor), not full shortest-path
    # routing to the destination. Good enough while topologies are
    # single-path; revisit with real path-cost routing for anything
    # with redundant links.
    while True:
        neighbors = [n for n in adjacency[current] if n not in visited]
        if not neighbors:
            break
        current = neighbors[0]
        visited.add(current)
        ordered_ids.append(current)
        device = store.get_device(current)
        if device and device.device_type == DeviceType.FIREWALL:
            break

    devices = [store.get_device(d) for d in ordered_ids]
    return [d for d in devices if d is not None]
