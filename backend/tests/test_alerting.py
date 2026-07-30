from datetime import datetime

from app.models import Device, Vendor, DeviceType, HealthSnapshot, Interface
from app.store import store
from app.alerting import check_health_alarms, check_interface_alarms


def setup_function():
    store.clear_all_for_tests()
    store.add_device(Device(
        device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
        vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL,
    ))


def test_no_alarm_below_threshold():
    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=40))
    assert store.list_alarms(active_only=True) == []


def test_critical_alarm_created_above_critical_threshold():
    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=95))
    alarms = store.list_alarms(active_only=True)
    assert len(alarms) == 1
    assert alarms[0].severity.value == "critical"
    assert alarms[0].metric == "cpu"


def test_medium_alarm_created_above_warning_threshold():
    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=80))
    alarms = store.list_alarms(active_only=True)
    assert len(alarms) == 1
    assert alarms[0].severity.value == "medium"


def test_alarm_does_not_duplicate_on_repeated_polls_at_same_severity():
    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=95))
    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=96))
    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=97))
    assert len(store.list_alarms(active_only=True)) == 1


def test_alarm_resolves_when_value_drops_back_below_threshold():
    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=95))
    assert len(store.list_alarms(active_only=True)) == 1

    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=30))
    assert store.list_alarms(active_only=True) == []
    all_alarms = store.list_alarms()
    assert len(all_alarms) == 1
    assert all_alarms[0].resolved_at is not None


def test_alarm_escalates_from_medium_to_critical():
    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=80))
    assert store.list_alarms(active_only=True)[0].severity.value == "medium"

    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=95))
    active = store.list_alarms(active_only=True)
    assert len(active) == 1
    assert active[0].severity.value == "critical"


def test_memory_threshold_independent_of_cpu():
    check_health_alarms("fw-1", HealthSnapshot(device_id="fw-1", timestamp=datetime.utcnow(), cpu_pct=10, memory_pct=95))
    active = store.list_alarms(active_only=True)
    assert len(active) == 1
    assert active[0].metric == "memory"


def test_interface_down_creates_high_alarm():
    check_interface_alarms("fw-1", [
        Interface(device_id="fw-1", if_name="eth1/1", admin_status="enabled", oper_status="down"),
    ])
    active = store.list_alarms(active_only=True)
    assert len(active) == 1
    assert active[0].severity.value == "high"
    assert active[0].metric == "interface_down:eth1/1"


def test_disabled_interface_does_not_alarm():
    check_interface_alarms("fw-1", [
        Interface(device_id="fw-1", if_name="eth1/2", admin_status="disabled", oper_status="down"),
    ])
    assert store.list_alarms(active_only=True) == []


def test_interface_alarm_resolves_when_it_comes_back_up():
    check_interface_alarms("fw-1", [Interface(device_id="fw-1", if_name="eth1/1", admin_status="enabled", oper_status="down")])
    assert len(store.list_alarms(active_only=True)) == 1
    check_interface_alarms("fw-1", [Interface(device_id="fw-1", if_name="eth1/1", admin_status="enabled", oper_status="up")])
    assert store.list_alarms(active_only=True) == []
