from datetime import datetime, timedelta

from app.models import Device, Vendor, DeviceType, ConfigBackup, Session
from app.store import store
from app.config_pipeline import parse_and_store

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
  </entry></devices>
</config>"""


def setup_function():
    store.clear_all_for_tests()


def test_parse_and_store_persists_routes_and_findings():
    device = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                     vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(device)
    backup = store.add_config_backup(ConfigBackup(
        device_id="fw-1", taken_at=datetime.utcnow(), status="success",
        size_bytes=len(PALOALTO_CONFIG), content=PALOALTO_CONFIG,
    ))

    parse_and_store(device, backup)

    parsed = store.get_parsed_config("fw-1")
    assert parsed is not None
    assert len(parsed["routes"]) == 1
    assert parsed["routes"][0]["destination_subnet"] == "0.0.0.0/0"
    # Default route is present, so no "missing default route" finding.
    assert not any("default route" in f["message"].lower() for f in parsed["findings"])


def test_parse_and_store_skips_failed_backups():
    device = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                     vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(device)
    backup = store.add_config_backup(ConfigBackup(
        device_id="fw-1", taken_at=datetime.utcnow(), status="failed", error="unreachable",
    ))

    parse_and_store(device, backup)

    assert store.get_parsed_config("fw-1") is None


def test_get_parsed_config_returns_none_when_never_parsed():
    assert store.get_parsed_config("nonexistent") is None


def test_session_snapshots_stored_and_searchable():
    sessions = [
        Session(device_id="fw-1", src_ip="10.1.1.5", src_port=1234, dst_ip="157.240.1.1",
                dst_port=443, protocol="tcp", state="active"),
        Session(device_id="fw-1", src_ip="10.1.1.9", src_port=5555, dst_ip="8.8.8.8",
                dst_port=53, protocol="udp", state="active"),
    ]
    store.add_sessions("fw-1", sessions)

    matches = store.search_sessions(device_id="fw-1", src_ip="10.1.1.5", dst_ip="157.240.1.1")
    assert len(matches) == 1
    assert matches[0].state == "active"

    no_match = store.search_sessions(device_id="fw-1", src_ip="10.1.1.5", dst_ip="1.2.3.4")
    assert no_match == []


def test_cleanup_old_sessions_removes_stale_rows():
    store.add_sessions("fw-1", [
        Session(device_id="fw-1", src_ip="10.1.1.5", src_port=1234, dst_ip="1.1.1.1",
                dst_port=443, protocol="tcp", state="active"),
    ])
    assert len(store.search_sessions(device_id="fw-1")) == 1

    # Everything just inserted is "now", so a cutoff in the future
    # should sweep it away.
    store.cleanup_old_sessions(datetime.utcnow() + timedelta(minutes=1))
    assert store.search_sessions(device_id="fw-1") == []
