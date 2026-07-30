from datetime import datetime
from unittest.mock import patch, MagicMock

from app.models import Device, Vendor, DeviceType, LogEvent, LogEventType, ConfigBackup
from app.store import store
from app.drivers.base import DriverNotSupported
from app.log_store import reset_log_store_for_tests
from app.troubleshooting import run_troubleshooting

PALOALTO_CONFIG = """<config>
  <devices><entry name="localhost.localdomain">
    <network>
      <virtual-router><entry name="default">
        <routing-table><ip><static-route>
          <entry name="default"><destination>0.0.0.0/0</destination>
            <nexthop><ip-address>203.0.113.1</ip-address></nexthop>
            <interface>ethernet1/1</interface></entry>
        </static-route></ip></routing-table>
      </entry></virtual-router>
    </network>
    <vsys><entry name="vsys1">
      <rulebase><nat><rules>
        <entry name="outbound-pat">
          <source><member>any</member></source>
          <destination><member>any</member></destination>
          <source-translation><dynamic-ip-and-port>
            <interface-address><interface>ethernet1/1</interface></interface-address>
          </dynamic-ip-and-port></source-translation>
        </entry>
      </rules></nat></rulebase>
    </entry></vsys>
  </entry></devices>
</config>"""


def setup_function():
    store.clear_all_for_tests()
    reset_log_store_for_tests()


def test_no_devices_onboarded():
    result = run_troubleshooting("10.1.1.5", "1.1.1.1")
    assert "No devices onboarded" in result.verdict


def test_firewall_traffic_log_shows_deny():
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw)
    store.add_logs([LogEvent(
        device_id="fw-1", timestamp=datetime.utcnow(), severity="info",
        event_type=LogEventType.TRAFFIC, src_ip="10.1.1.5", dst_ip="157.240.1.1",
        action="deny", matched_rule="Block-Social-Media",
    )])

    result = run_troubleshooting("10.1.1.5", "157.240.1.1")

    traffic_step = next(s for s in result.steps if s.stage == "firewall_traffic")
    assert traffic_step.status == "fail"
    assert "deny" in traffic_step.summary
    assert traffic_step.detail["matched_rule"] == "Block-Social-Media"
    assert "fw-1" in result.verdict
    assert "Block-Social-Media" in result.verdict


def test_firewall_traffic_never_reached():
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw)

    result = run_troubleshooting("10.1.1.5", "157.240.1.1")

    traffic_step = next(s for s in result.steps if s.stage == "firewall_traffic")
    assert traffic_step.status == "fail"
    assert traffic_step.summary == "Traffic never reached firewall."
    assert traffic_step.source == "traffic_log"


def test_allowed_traffic_with_return_traffic_passes():
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw)
    store.add_logs([
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info",
                 event_type=LogEventType.TRAFFIC, src_ip="10.1.1.5", dst_ip="157.240.1.1", action="allow"),
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info",
                 event_type=LogEventType.TRAFFIC, src_ip="157.240.1.1", dst_ip="10.1.1.5", action="allow"),
    ])

    result = run_troubleshooting("10.1.1.5", "157.240.1.1")

    traffic_step = next(s for s in result.steps if s.stage == "firewall_traffic")
    return_step = next(s for s in result.steps if s.stage == "return_traffic")
    assert traffic_step.status == "pass"
    assert return_step.status == "pass"


@patch("app.troubleshooting.get_driver")
def test_router_step_reports_no_router_log_when_driver_lacks_sessions(mock_get_driver):
    rt = Device(device_id="rt-1", hostname="rt1", mgmt_ip="10.0.0.2",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.ROUTER)
    store.add_device(rt)

    mock_driver = MagicMock()
    mock_driver.get_sessions.side_effect = DriverNotSupported("no flow cache")
    mock_get_driver.return_value = mock_driver

    result = run_troubleshooting("10.1.1.5", "157.240.1.1")

    router_step = next(s for s in result.steps if s.stage == "router_log")
    assert router_step.status == "fail"
    assert router_step.summary == "No router log found."


@patch("app.troubleshooting.get_driver")
def test_router_step_passes_when_session_found(mock_get_driver):
    from app.models import Session
    rt = Device(device_id="rt-1", hostname="rt1", mgmt_ip="10.0.0.2",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.ROUTER)
    store.add_device(rt)

    mock_driver = MagicMock()
    mock_driver.get_sessions.return_value = [
        Session(device_id="rt-1", src_ip="10.1.1.5", dst_ip="157.240.1.1",
                src_port=1234, dst_port=443, protocol="tcp"),
    ]
    mock_get_driver.return_value = mock_driver

    result = run_troubleshooting("10.1.1.5", "157.240.1.1")

    router_step = next(s for s in result.steps if s.stage == "router_log")
    assert router_step.status == "pass"
    assert router_step.source == "session_log"


def test_nat_and_routing_steps_use_config_backup():
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw)
    store.add_config_backup(ConfigBackup(
        device_id="fw-1", taken_at=datetime.utcnow(), status="success",
        size_bytes=len(PALOALTO_CONFIG), content=PALOALTO_CONFIG,
    ))

    result = run_troubleshooting("10.1.1.5", "8.8.8.8")

    nat_step = next(s for s in result.steps if s.stage == "nat")
    routing_step = next(s for s in result.steps if s.stage == "routing")
    assert nat_step.status == "pass"
    assert nat_step.source == "config_file"
    assert routing_step.status == "pass"
    assert routing_step.detail["is_default_route"] is True


def test_nat_and_routing_steps_honest_when_no_config_backup():
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw)

    result = run_troubleshooting("10.1.1.5", "8.8.8.8")

    nat_step = next(s for s in result.steps if s.stage == "nat")
    routing_step = next(s for s in result.steps if s.stage == "routing")
    assert nat_step.status == "not_applicable"
    assert "configuration backup" in nat_step.summary.lower()
    assert routing_step.status == "not_applicable"


def test_device_id_filter_scopes_to_one_device():
    fw1 = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                 vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    fw2 = Device(device_id="fw-2", hostname="fw2", mgmt_ip="10.0.0.2",
                 vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw1)
    store.add_device(fw2)

    result = run_troubleshooting("10.1.1.5", "157.240.1.1", device_id="fw-1")

    device_ids = {s.device_id for s in result.steps}
    assert device_ids == {"fw-1"}
