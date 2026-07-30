"""
Proves the store is genuinely DB-backed: data written through one
Store()/TopologyStore() instance is visible from a second, freshly
constructed instance -- which would NOT be true of the old in-memory
implementation (a new instance there would start empty).
"""
from datetime import datetime

from app.models import Device, Vendor, DeviceType, HealthSnapshot, Identity
from app.store import Store
from app.topology import TopologyStore
from app.models import TopologyLink


def setup_function():
    Store().clear_all_for_tests()
    TopologyStore().clear()


def test_device_persists_across_store_instances():
    store_a = Store()
    store_a.add_device(Device(
        device_id="dev-1", hostname="fw1", mgmt_ip="10.0.0.1",
        vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL,
    ))

    store_b = Store()  # a second, independent instance
    fetched = store_b.get_device("dev-1")
    assert fetched is not None
    assert fetched.hostname == "fw1"


def test_health_history_persists_across_store_instances():
    store_a = Store()
    store_a.add_device(Device(
        device_id="dev-2", hostname="sw1", mgmt_ip="10.0.0.2",
        vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH,
    ))
    store_a.add_health_snapshot(HealthSnapshot(
        device_id="dev-2", timestamp=datetime.utcnow(), cpu_pct=42.0,
    ))

    store_b = Store()
    history = store_b.get_health_history("dev-2")
    assert len(history) == 1
    assert history[0].cpu_pct == 42.0


def test_topology_links_persist_across_instances():
    topo_a = TopologyStore()
    topo_a.add_manual_link(TopologyLink(device_a="a", interface_a="Gi1", device_b="b", interface_b="Gi2"))

    topo_b = TopologyStore()
    links = topo_b.list_links()
    assert len(links) == 1
    assert links[0].device_a == "a"


def test_identity_resolves_by_ip_and_time_window():
    store_a = Store()
    store_a.add_identity(Identity(
        username="vish", ip_address="10.1.1.5", mac_address="aa:bb:cc:00:11:22",
        valid_from=datetime(2026, 1, 1), valid_to=datetime(2026, 12, 31),
    ))

    store_b = Store()
    resolved = store_b.resolve_identity("10.1.1.5", at_time=datetime(2026, 6, 1))
    assert resolved is not None
    assert resolved.username == "vish"

    # outside the valid window -> no match
    assert store_b.resolve_identity("10.1.1.5", at_time=datetime(2027, 1, 1)) is None
