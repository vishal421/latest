"""
Drift detection: compares the admin's manually-drawn topology against
what CDP/LLDP discovery actually finds, and flags mismatches. This is
the piece Phase 2/3 deliberately left out ("gets both data sources
populated correctly so drift detection has something to compare
later") -- now that both sets of links exist, this does the comparing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.topology import topology_store


@dataclass
class DriftEntry:
    device_a: str
    device_b: str
    drift_type: str  # "missing_discovered" | "missing_manual" | "interface_mismatch"
    manual_interfaces: Optional[tuple] = None
    discovered_interfaces: Optional[tuple] = None


def _pair_key(link) -> tuple:
    return tuple(sorted([link.device_a, link.device_b]))


def compute_drift() -> list[DriftEntry]:
    manual = topology_store.list_links(source="manual")
    discovered = topology_store.list_links(source="discovered")

    manual_by_pair = {_pair_key(l): l for l in manual}
    discovered_by_pair = {_pair_key(l): l for l in discovered}

    drifts: list[DriftEntry] = []
    for pair in set(manual_by_pair) | set(discovered_by_pair):
        m = manual_by_pair.get(pair)
        d = discovered_by_pair.get(pair)

        if m and not d:
            drifts.append(DriftEntry(
                device_a=pair[0], device_b=pair[1], drift_type="missing_discovered",
                manual_interfaces=(m.interface_a, m.interface_b),
            ))
        elif d and not m:
            drifts.append(DriftEntry(
                device_a=pair[0], device_b=pair[1], drift_type="missing_manual",
                discovered_interfaces=(d.interface_a, d.interface_b),
            ))
        else:
            # Both exist for this device pair -- check the interfaces
            # actually match (a device_id -> if_name mapping, so it's
            # order-independent regardless of which side is device_a).
            m_ifaces = {m.device_a: m.interface_a, m.device_b: m.interface_b}
            d_ifaces = {d.device_a: d.interface_a, d.device_b: d.interface_b}
            if m_ifaces != d_ifaces:
                drifts.append(DriftEntry(
                    device_a=pair[0], device_b=pair[1], drift_type="interface_mismatch",
                    manual_interfaces=(m.interface_a, m.interface_b),
                    discovered_interfaces=(d.interface_a, d.interface_b),
                ))
    return drifts
