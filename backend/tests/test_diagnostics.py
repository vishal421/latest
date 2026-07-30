from unittest.mock import patch, MagicMock

from app.models import Device, Vendor, DeviceType, PolicyRule, RouteEntry, MacArpEntry
from app.store import store
from app.diagnostics import run_diagnostics


def setup_function():
    store.clear_all_for_tests()


@patch("app.diagnostics.get_driver")
def test_diagnostics_reports_deny_as_root_cause(mock_get_driver):
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw)

    mock_driver = MagicMock()
    mock_driver.test_policy_match.return_value = PolicyRule(
        device_id="fw-1", rule_id="24", name="Block-Social-Media", action="deny",
    )
    mock_driver.get_sessions.return_value = []
    mock_driver.get_logs.return_value = []
    mock_get_driver.return_value = mock_driver

    result = run_diagnostics("10.1.1.5", "157.240.1.1", 443, "tcp")

    assert result.hops[0].passed is False
    assert "Block-Social-Media" in result.verdict
    assert "fw-1" in result.verdict


@patch("app.diagnostics.get_driver")
def test_diagnostics_reports_allow_when_no_blocking_rule(mock_get_driver):
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw)

    mock_driver = MagicMock()
    mock_driver.test_policy_match.return_value = PolicyRule(
        device_id="fw-1", rule_id="1", name="allow-web", action="allow",
    )
    mock_driver.get_sessions.return_value = []
    mock_driver.get_logs.return_value = []
    mock_get_driver.return_value = mock_driver

    result = run_diagnostics("10.1.1.5", "1.1.1.1", 443, "tcp")

    assert result.hops[0].passed is True
    assert "no blocking device found" in result.verdict.lower()


def test_diagnostics_with_no_devices_onboarded():
    result = run_diagnostics("10.1.1.5", "1.1.1.1", 443, "tcp")
    assert result.hops == []
    assert "No devices onboarded" in result.verdict


@patch("app.diagnostics.get_driver")
def test_diagnostics_full_hop_chain_order_and_switch_failure(mock_get_driver):
    """Switch/router/firewall hops should run in that order, and a
    switch-level failure (host not seen on the switch) should surface
    as the root cause even though a router and firewall are also
    onboarded."""
    sw = Device(device_id="sw-1", hostname="sw1", mgmt_ip="10.0.0.5",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    rt = Device(device_id="rt-1", hostname="rt1", mgmt_ip="10.0.0.1",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.ROUTER)
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.2",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(sw)
    store.add_device(rt)
    store.add_device(fw)

    def driver_for(device):
        m = MagicMock()
        if device.device_id == "sw-1":
            m.get_arp_mac_table.return_value = []  # src_ip NOT found -> hop fails
        elif device.device_id == "rt-1":
            m.get_route.return_value = [RouteEntry(
                device_id="rt-1", destination_subnet="157.240.1.1",
                next_hop="10.0.0.254", protocol="ospf",
            )]
        elif device.device_id == "fw-1":
            m.test_policy_match.return_value = PolicyRule(
                device_id="fw-1", rule_id="1", name="allow-web", action="allow",
            )
            m.get_sessions.return_value = []
            m.get_logs.return_value = []
        return m

    mock_get_driver.side_effect = driver_for

    result = run_diagnostics("10.1.1.5", "157.240.1.1", 443, "tcp")

    assert [h.hop_type for h in result.hops] == ["switch", "router", "firewall"]
    assert result.hops[0].passed is False
    assert result.hops[1].passed is True
    assert result.hops[2].passed is True
    assert "switch" in result.verdict.lower()
    assert "sw-1" in result.verdict


@patch("app.diagnostics.get_driver")
def test_diagnostics_verdict_names_known_identity(mock_get_driver):
    from datetime import datetime
    from app.models import Identity

    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw)
    store.add_identity(Identity(
        username="vish", ip_address="10.1.1.5", mac_address=None,
        valid_from=datetime(2020, 1, 1), valid_to=None,
    ))

    mock_driver = MagicMock()
    mock_driver.test_policy_match.return_value = PolicyRule(
        device_id="fw-1", rule_id="24", name="Block-Social-Media", action="deny",
    )
    mock_driver.get_sessions.return_value = []
    mock_driver.get_logs.return_value = []
    mock_get_driver.return_value = mock_driver

    result = run_diagnostics("10.1.1.5", "157.240.1.1", 443, "tcp")
    assert "vish" in result.verdict
    assert "10.1.1.5" in result.verdict
