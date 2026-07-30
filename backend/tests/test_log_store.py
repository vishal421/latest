from datetime import datetime

from app.models import LogEvent, LogEventType
from app.log_store import reset_log_store_for_tests, get_log_store


def setup_function():
    reset_log_store_for_tests()


def test_search_filters_by_event_type():
    store = get_log_store()
    store.add([
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info", event_type=LogEventType.TRAFFIC, src_ip="10.1.1.5"),
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="critical", event_type=LogEventType.THREAT, threat_name="Trojan.Generic"),
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info", event_type=LogEventType.URL, url="example.com", category="Business"),
    ])
    threat_only = store.search(event_type="threat")
    assert len(threat_only) == 1
    assert threat_only[0].threat_name == "Trojan.Generic"

    url_only = store.search(event_type="url")
    assert len(url_only) == 1
    assert url_only[0].url == "example.com"


def test_search_without_event_type_returns_all():
    store = get_log_store()
    store.add([
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info", event_type=LogEventType.TRAFFIC),
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info", event_type=LogEventType.SYSTEM),
    ])
    assert len(store.search()) == 2
