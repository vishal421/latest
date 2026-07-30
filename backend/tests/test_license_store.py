from datetime import datetime

from app.models import License
from app.store import store


def setup_function():
    store.clear_all_for_tests()


def test_set_and_get_licenses():
    store.set_licenses("fw-1", [
        License(device_id="fw-1", feature="Threat Prevention", status="active", expiry_date=datetime(2027, 1, 1)),
        License(device_id="fw-1", feature="URL Filtering", status="active", expiry_date=datetime(2026, 3, 15)),
    ])
    licenses = store.get_licenses("fw-1")
    assert len(licenses) == 2
    assert {l.feature for l in licenses} == {"Threat Prevention", "URL Filtering"}


def test_set_licenses_replaces_previous_snapshot():
    store.set_licenses("fw-1", [License(device_id="fw-1", feature="Old Feature", status="active")])
    store.set_licenses("fw-1", [License(device_id="fw-1", feature="New Feature", status="active")])
    licenses = store.get_licenses("fw-1")
    assert len(licenses) == 1
    assert licenses[0].feature == "New Feature"


def test_get_licenses_without_device_filter_returns_all():
    store.set_licenses("fw-1", [License(device_id="fw-1", feature="A", status="active")])
    store.set_licenses("fw-2", [License(device_id="fw-2", feature="B", status="active")])
    assert len(store.get_licenses()) == 2
