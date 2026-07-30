from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models import Device, Vendor, DeviceType, Interface, Alarm, AlarmSeverity
from app.store import store
from app.topology_status import classify_interface, build_status_snapshot, snapshot_fingerprint

client = TestClient(app)


def setup_function():
    store.clear_all_for_tests()


def _device(device_id="sw-1"):
    d = Device(device_id=device_id, hostname=device_id, mgmt_ip="10.0.0.1",
               vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    store.add_device(d)
    return d


def test_classify_interface_states():
    up = Interface(device_id="d", if_name="eth0", admin_status="enabled", oper_status="up")
    down = Interface(device_id="d", if_name="eth1", admin_status="enabled", oper_status="down")
    admin_down = Interface(device_id="d", if_name="eth2", admin_status="disabled", oper_status="down")
    unknown = Interface(device_id="d", if_name="eth3", admin_status="unknown", oper_status="unknown")
    errored = Interface(device_id="d", if_name="eth4", admin_status="enabled", oper_status="up", errors=999)

    assert classify_interface(up) == "up"
    assert classify_interface(down) == "down"
    assert classify_interface(admin_down) == "admin_down"
    assert classify_interface(unknown) == "unknown"
    assert classify_interface(errored) == "error"


def test_build_status_snapshot_rolls_up_worst_alarm_per_device():
    _device("sw-1")
    store.set_interface_stats("sw-1", [Interface(device_id="sw-1", if_name="Gi0/1", admin_status="enabled", oper_status="down")])
    store.create_alarm(Alarm(device_id="sw-1", severity=AlarmSeverity.MEDIUM, metric="cpu",
                              description="CPU high", triggered_at=datetime.utcnow()))
    store.create_alarm(Alarm(device_id="sw-1", severity=AlarmSeverity.CRITICAL, metric="interface_down:Gi0/1",
                              description="Gi0/1 is down", triggered_at=datetime.utcnow(), detail={"interface": "Gi0/1"}))

    snap = build_status_snapshot()
    dev = snap["devices"]["sw-1"]
    assert dev["status"] == "critical"
    assert dev["alarm_count"] == 2
    assert dev["alarms"][0]["severity"] == "critical"  # worst first
    assert dev["alarms"][0]["severity_label"] == "Critical"
    assert snap["interfaces"]["sw-1"]["Gi0/1"]["classification"] == "down"


def test_device_with_no_alarms_is_ok():
    _device("sw-2")
    snap = build_status_snapshot()
    assert snap["devices"]["sw-2"]["status"] == "ok"
    assert snap["devices"]["sw-2"]["alarm_count"] == 0


def test_fingerprint_changes_when_snapshot_changes():
    _device("sw-3")
    snap1 = build_status_snapshot()
    fp1 = snapshot_fingerprint(snap1)
    store.create_alarm(Alarm(device_id="sw-3", severity=AlarmSeverity.LOW, metric="cpu",
                              description="minor", triggered_at=datetime.utcnow()))
    snap2 = build_status_snapshot()
    fp2 = snapshot_fingerprint(snap2)
    assert fp1 != fp2


def test_diagram_get_includes_status_block():
    _device("sw-4")
    resp = client.get("/network-diagram")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "devices" in body["status"]


def test_status_endpoint():
    _device("sw-5")
    resp = client.get("/network-diagram/status")
    assert resp.status_code == 200
    assert "sw-5" in resp.json()["devices"]
