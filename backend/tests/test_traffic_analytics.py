from datetime import datetime

from app.models import LogEvent, LogEventType
from app.log_store import reset_log_store_for_tests, get_log_store
from app.traffic_analytics import top_source_ips, top_destination_ips, top_applications, denied_traffic


def setup_function():
    reset_log_store_for_tests()


def _seed():
    store = get_log_store()
    store.add([
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info", event_type=LogEventType.TRAFFIC,
                  src_ip="10.1.1.5", dst_ip="1.1.1.1", app="dns", action="allow", bytes_total=1000),
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info", event_type=LogEventType.TRAFFIC,
                  src_ip="10.1.1.5", dst_ip="157.240.1.1", app="ssl", action="allow", bytes_total=50000),
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info", event_type=LogEventType.TRAFFIC,
                  src_ip="10.1.1.9", dst_ip="157.240.1.1", app="ssl", action="allow", bytes_total=20000),
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info", event_type=LogEventType.TRAFFIC,
                  src_ip="10.1.1.9", dst_ip="45.33.32.156", app="ssl", action="deny", matched_rule="Block-Known-Malicious"),
        LogEvent(device_id="fw-1", timestamp=datetime.utcnow(), severity="info", event_type=LogEventType.THREAT,
                  src_ip="10.1.1.9", dst_ip="45.33.32.156"),  # not a traffic log -- must be excluded
    ])


def test_top_source_ips_ranks_by_byte_volume():
    _seed()
    result = top_source_ips()
    assert result[0]["key"] == "10.1.1.5"  # 1000 + 50000 = 51000 bytes, more than 10.1.1.9's 20000
    assert result[0]["bytes_total"] == 51000
    assert result[0]["count"] == 2


def test_top_destination_ips_ranks_by_byte_volume():
    _seed()
    result = top_destination_ips()
    assert result[0]["key"] == "157.240.1.1"
    assert result[0]["bytes_total"] == 70000


def test_top_applications_aggregates_across_sources():
    _seed()
    result = top_applications()
    ssl = next(r for r in result if r["key"] == "ssl")
    assert ssl["bytes_total"] == 70000
    assert ssl["count"] == 3  # 2 allowed ssl flows with bytes + 1 denied ssl flow with no byte count, still a hit


def test_denied_traffic_only_includes_deny_action():
    _seed()
    result = denied_traffic()
    assert len(result) == 1
    assert result[0]["dst_ip"] == "45.33.32.156"
    assert result[0]["matched_rule"] == "Block-Known-Malicious"
    assert result[0]["hits"] == 1


def test_threat_logs_excluded_from_traffic_aggregation():
    _seed()
    # the seeded THREAT log has src_ip=10.1.1.9 with no bytes -- if it
    # leaked into traffic aggregation it would inflate 10.1.1.9's count
    result = top_source_ips()
    src_9 = next(r for r in result if r["key"] == "10.1.1.9")
    assert src_9["count"] == 2  # only the 2 real traffic logs, not the threat log


def test_total_traffic_bytes_sums_all_traffic_logs():
    from app.traffic_analytics import total_traffic_bytes
    _seed()
    # 1000 + 50000 + 20000 + 0 (deny log has no bytes_total) = 71000
    assert total_traffic_bytes() == 71000
