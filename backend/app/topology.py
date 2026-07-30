"""
Topology engine.

TopologyStore is now backed by the same database as the rest of the
persistent store (see store.py) -- manual links and CDP/LLDP-discovered
links both survive a restart. Discovery still replaces the whole
discovered set on each run (drop + reinsert) since it's meant to
reflect current live reality, not accumulate stale entries.
"""
from __future__ import annotations

from app.models import TopologyLink, DiscoveredNeighbor
from app.drivers.factory import get_driver
from app.store import store
from app.db import get_session
from app.db_models import TopologyLinkRow


def _row_to_link(row: TopologyLinkRow) -> TopologyLink:
    return TopologyLink(
        device_a=row.device_a, interface_a=row.interface_a,
        device_b=row.device_b, interface_b=row.interface_b, source=row.source,
    )


class TopologyStore:
    def add_manual_link(self, link: TopologyLink) -> None:
        link.source = "manual"
        with get_session() as session:
            session.add(TopologyLinkRow(
                device_a=link.device_a, interface_a=link.interface_a,
                device_b=link.device_b, interface_b=link.interface_b, source="manual",
            ))
            session.commit()

    def list_links(self, source: str | None = None) -> list[TopologyLink]:
        with get_session() as session:
            query = session.query(TopologyLinkRow)
            if source:
                query = query.filter(TopologyLinkRow.source == source)
            return [_row_to_link(r) for r in query.all()]

    def replace_discovered_links(self, links: list[TopologyLink]) -> None:
        """Discovery runs fresh each time -- drop the old discovered
        set and replace it, keep manual links untouched."""
        with get_session() as session:
            session.query(TopologyLinkRow).filter(TopologyLinkRow.source == "discovered").delete()
            for link in links:
                session.add(TopologyLinkRow(
                    device_a=link.device_a, interface_a=link.interface_a,
                    device_b=link.device_b, interface_b=link.interface_b, source="discovered",
                ))
            session.commit()

    def clear(self) -> None:
        """Test-only helper."""
        with get_session() as session:
            session.query(TopologyLinkRow).delete()
            session.commit()


topology_store = TopologyStore()


def _resolve_neighbor_device_id(neighbor: DiscoveredNeighbor) -> str | None:
    """Match a raw CDP/LLDP neighbor (hostname/IP) against onboarded
    devices. Returns None if the neighbor isn't an onboarded device
    (e.g. an end-host or a device InfraOS doesn't manage yet)."""
    for device in store.list_devices():
        if neighbor.neighbor_mgmt_ip and device.mgmt_ip == neighbor.neighbor_mgmt_ip:
            return device.device_id
        if device.hostname and neighbor.neighbor_hostname.startswith(device.hostname):
            return device.device_id
    return None


def run_discovery() -> list[TopologyLink]:
    """Calls get_neighbors() on every onboarded device that supports it
    (Cisco router/switch in Phase 2) and resolves the results into
    TopologyLinks between onboarded devices."""
    discovered: list[TopologyLink] = []
    seen_pairs = set()

    for device in store.list_devices():
        try:
            driver = get_driver(device)
            driver.connect()
            neighbors = driver.get_neighbors()
        except Exception:
            continue  # device/driver doesn't support discovery -- skip it, not an error

        for neighbor in neighbors:
            neighbor_device_id = _resolve_neighbor_device_id(neighbor)
            if not neighbor_device_id:
                continue
            pair_key = tuple(sorted([device.device_id, neighbor_device_id]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            discovered.append(TopologyLink(
                device_a=device.device_id,
                interface_a=neighbor.local_interface,
                device_b=neighbor_device_id,
                interface_b=neighbor.neighbor_interface,
                source="discovered",
            ))

    topology_store.replace_discovered_links(discovered)
    return discovered
