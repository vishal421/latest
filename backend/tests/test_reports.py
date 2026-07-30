from datetime import datetime, timedelta

from app.models import Device, Vendor, DeviceType, Alarm, AlarmSeverity, License
from app.store import store
from app.reports import generate_summary_report


def setup_function():
    store.clear_all_for_tests()


def test_report_reflects_real_device_counts_by_vendor():
    store.add_device(Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1", vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL))
    store.add_device(Device(device_id="fw-2", hostname="fw2", mgmt_ip="10.0.0.2", vendor=Vendor.FORTIGATE, device_type=DeviceType.FIREWALL))
    report = generate_summary_report()
    assert report["devices"]["total"] == 2
    assert report["devices"]["by_vendor"] == {"paloalto": 1, "fortigate": 1}


def test_report_counts_active_and_windowed_alarms():
    store.create_alarm(Alarm(device_id="fw-1", severity=AlarmSeverity.CRITICAL, metric="cpu",
                              description="CPU high", triggered_at=datetime.utcnow()))
    report = generate_summary_report()
    assert report["alarms"]["currently_active"] == 1
    assert report["alarms"]["active_critical"] == 1
    assert report["alarms"]["triggered_in_window"] == 1


def test_report_lists_licenses_expiring_within_30_days():
    store.set_licenses("fw-1", [
        License(device_id="fw-1", feature="Threat Prevention", status="active", expiry_date=datetime.utcnow() + timedelta(days=10)),
        License(device_id="fw-1", feature="URL Filtering", status="active", expiry_date=datetime.utcnow() + timedelta(days=200)),
    ])
    report = generate_summary_report()
    assert report["licenses"]["total_tracked"] == 2
    assert len(report["licenses"]["expiring_within_30_days"]) == 1
    assert report["licenses"]["expiring_within_30_days"][0]["feature"] == "Threat Prevention"

