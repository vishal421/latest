from app.models import TopologyLink
from app.topology import topology_store
from app.drift import compute_drift


def setup_function():
    topology_store.clear()


def test_no_drift_when_manual_and_discovered_match():
    topology_store.add_manual_link(TopologyLink(device_a="sw-1", interface_a="Gi0/1", device_b="rt-1", interface_b="Gi1"))
    topology_store.replace_discovered_links([
        TopologyLink(device_a="sw-1", interface_a="Gi0/1", device_b="rt-1", interface_b="Gi1", source="discovered"),
    ])
    assert compute_drift() == []


def test_drift_when_manual_link_not_seen_live():
    topology_store.add_manual_link(TopologyLink(device_a="sw-1", interface_a="Gi0/1", device_b="rt-1", interface_b="Gi1"))
    drifts = compute_drift()
    assert len(drifts) == 1
    assert drifts[0].drift_type == "missing_discovered"


def test_drift_when_discovered_link_never_drawn():
    topology_store.replace_discovered_links([
        TopologyLink(device_a="sw-1", interface_a="Gi0/1", device_b="rt-1", interface_b="Gi1", source="discovered"),
    ])
    drifts = compute_drift()
    assert len(drifts) == 1
    assert drifts[0].drift_type == "missing_manual"


def test_drift_when_interfaces_dont_match():
    topology_store.add_manual_link(TopologyLink(device_a="sw-1", interface_a="Gi0/1", device_b="rt-1", interface_b="Gi1"))
    topology_store.replace_discovered_links([
        # same device pair, but discovery says it's actually on Gi0/7 / Gi3
        TopologyLink(device_a="sw-1", interface_a="Gi0/7", device_b="rt-1", interface_b="Gi3", source="discovered"),
    ])
    drifts = compute_drift()
    assert len(drifts) == 1
    assert drifts[0].drift_type == "interface_mismatch"
    assert drifts[0].manual_interfaces == ("Gi0/1", "Gi1")
    assert drifts[0].discovered_interfaces == ("Gi0/7", "Gi3")
