from unittest.mock import patch, MagicMock

from app.models import Device, Vendor, DeviceType, TopologyLink, MacArpEntry
from app.store import store
from app.topology import topology_store
from app.path_selection import find_path_devices


def setup_function():
    store.clear_all_for_tests()
    topology_store.clear()


def test_returns_none_when_no_topology_links():
    sw = Device(device_id="sw-1", hostname="sw1", mgmt_ip="10.0.0.5",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    store.add_device(sw)
    assert find_path_devices("10.1.1.5", "1.1.1.1") is None


@patch("app.path_selection.get_driver")
def test_returns_none_when_source_not_found_on_any_switch(mock_get_driver):
    sw = Device(device_id="sw-1", hostname="sw1", mgmt_ip="10.0.0.5",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    store.add_device(sw)
    topology_store.add_manual_link(TopologyLink(device_a="sw-1", interface_a="Gi0/1", device_b="rt-1", interface_b="Gi1"))

    mock_driver = MagicMock()
    mock_driver.get_arp_mac_table.return_value = []  # src_ip not present anywhere
    mock_get_driver.return_value = mock_driver

    assert find_path_devices("10.1.1.5", "1.1.1.1") is None


@patch("app.path_selection.get_driver")
def test_walks_switch_router_firewall_chain(mock_get_driver):
    sw = Device(device_id="sw-1", hostname="sw1", mgmt_ip="10.0.0.5",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    rt = Device(device_id="rt-1", hostname="rt1", mgmt_ip="10.0.0.1",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.ROUTER)
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.2",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(sw)
    store.add_device(rt)
    store.add_device(fw)

    topology_store.add_manual_link(TopologyLink(device_a="sw-1", interface_a="Gi0/1", device_b="rt-1", interface_b="Gi1"))
    topology_store.add_manual_link(TopologyLink(device_a="rt-1", interface_a="Gi2", device_b="fw-1", interface_b="eth1/1"))

    def driver_for(device):
        m = MagicMock()
        if device.device_id == "sw-1":
            m.get_arp_mac_table.return_value = [
                MacArpEntry(device_id="sw-1", mac_address="aa:bb", ip_address="10.1.1.5", vlan_id=10, interface="Gi0/5"),
            ]
        return m

    mock_get_driver.side_effect = driver_for

    path = find_path_devices("10.1.1.5", "157.240.1.1")
    assert [d.device_id for d in path] == ["sw-1", "rt-1", "fw-1"]


@patch("app.path_selection.get_driver")
def test_stops_at_first_firewall_even_with_more_graph_beyond(mock_get_driver):
    sw = Device(device_id="sw-1", hostname="sw1", mgmt_ip="10.0.0.5",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.2",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    isp_edge = Device(device_id="rt-2", hostname="isp-edge", mgmt_ip="10.0.0.9",
                       vendor=Vendor.CISCO_IOS, device_type=DeviceType.ROUTER)
    store.add_device(sw)
    store.add_device(fw)
    store.add_device(isp_edge)

    topology_store.add_manual_link(TopologyLink(device_a="sw-1", interface_a="Gi0/1", device_b="fw-1", interface_b="eth1/1"))
    topology_store.add_manual_link(TopologyLink(device_a="fw-1", interface_a="eth1/2", device_b="rt-2", interface_b="Gi1"))

    def driver_for(device):
        m = MagicMock()
        if device.device_id == "sw-1":
            m.get_arp_mac_table.return_value = [
                MacArpEntry(device_id="sw-1", mac_address="aa:bb", ip_address="10.1.1.5", vlan_id=10, interface="Gi0/5"),
            ]
        return m

    mock_get_driver.side_effect = driver_for

    path = find_path_devices("10.1.1.5", "1.1.1.1")
    assert [d.device_id for d in path] == ["sw-1", "fw-1"]
