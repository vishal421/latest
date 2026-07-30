from unittest.mock import patch, MagicMock

from app.models import Device, Vendor, DeviceType, DiscoveredNeighbor
from app.store import store
from app.topology import topology_store, run_discovery


def setup_function():
    store.clear_all_for_tests()
    topology_store.clear()


@patch("app.topology.get_driver")
def test_discovery_resolves_neighbor_by_mgmt_ip(mock_get_driver):
    rt = Device(device_id="rt-1", hostname="rt1", mgmt_ip="10.0.0.1",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.ROUTER)
    sw = Device(device_id="sw-1", hostname="sw1", mgmt_ip="10.0.0.5",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    store.add_device(rt)
    store.add_device(sw)

    def driver_for(device):
        m = MagicMock()
        if device.device_id == "rt-1":
            m.get_neighbors.return_value = [DiscoveredNeighbor(
                device_id="rt-1", local_interface="Gi1",
                neighbor_hostname="sw1.example.com",
                neighbor_interface="Gi0/1", neighbor_mgmt_ip="10.0.0.5",
            )]
        else:
            m.get_neighbors.return_value = []
        return m

    mock_get_driver.side_effect = driver_for

    links = run_discovery()

    assert len(links) == 1
    assert {links[0].device_a, links[0].device_b} == {"rt-1", "sw-1"}
    assert links[0].source == "discovered"


@patch("app.topology.get_driver")
def test_discovery_skips_unresolvable_neighbors(mock_get_driver):
    rt = Device(device_id="rt-1", hostname="rt1", mgmt_ip="10.0.0.1",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.ROUTER)
    store.add_device(rt)

    mock_driver = MagicMock()
    mock_driver.get_neighbors.return_value = [DiscoveredNeighbor(
        device_id="rt-1", local_interface="Gi1",
        neighbor_hostname="unknown-device", neighbor_interface="Gi0/1",
        neighbor_mgmt_ip="192.168.99.99",
    )]
    mock_get_driver.return_value = mock_driver

    links = run_discovery()
    assert links == []


def test_manual_links_survive_discovery_refresh():
    from app.models import TopologyLink
    topology_store.add_manual_link(TopologyLink(
        device_a="a", interface_a="Gi1", device_b="b", interface_b="Gi2",
    ))
    with patch("app.topology.get_driver"):
        run_discovery()
    manual = topology_store.list_links(source="manual")
    assert len(manual) == 1
