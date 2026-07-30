from unittest.mock import patch

from app.models import Device, Vendor, DeviceType
from app.drivers.fortigate import FortigateDriver


class FakeResponse:
    def __init__(self, json_data=None, status=200):
        self._json = json_data or {}
        self.status_code = status

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class FakeHttpClient:
    def __init__(self, json_by_path: dict):
        self.json_by_path = json_by_path
        self.calls = []

    def get(self, url, headers=None, params=None, verify=None, timeout=None):
        self.calls.append(url)
        for path_fragment, payload in self.json_by_path.items():
            if path_fragment in url:
                return FakeResponse(json_data=payload)
        return FakeResponse(json_data={})


def make_device():
    return Device(
        device_id="fw-2", hostname="fgt1", mgmt_ip="10.0.0.2",
        vendor=Vendor.FORTIGATE, device_type=DeviceType.FIREWALL,
    )


def test_get_facts_parses_system_status():
    fake = FakeHttpClient({
        "monitor/system/status": {"results": {
            "model_name": "FortiGate-100F", "version": "v7.4.1",
            "serial": "FG100F1234", "hostname": "fgt1",
        }},
    })
    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=fake)
    device = driver.get_facts()
    assert device.model == "FortiGate-100F"
    assert device.os_version == "v7.4.1"
    assert device.serial_number == "FG100F1234"


def test_get_interfaces_parses_link_state():
    fake = FakeHttpClient({
        "monitor/system/interface": {"results": {
            "port1": {"link": True, "ip": "10.0.0.2"},
            "port2": {"link": False, "ip": None},
        }},
    })
    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=fake)
    interfaces = driver.get_interfaces()
    by_name = {i.if_name: i for i in interfaces}
    assert by_name["port1"].status == "up"
    assert by_name["port2"].status == "down"


def test_get_policy_rules_parses_action_and_addresses():
    fake = FakeHttpClient({
        "cmdb/firewall/policy": {"results": [
            {"policyid": 12, "name": "block-social", "action": "deny",
             "srcaddr": "all", "dstaddr": "social-media-group"},
        ]},
    })
    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=fake)
    rules = driver.get_policy_rules()
    assert rules[0].rule_id == "12"
    assert rules[0].action == "deny"


@patch.object(FortigateDriver, "open_cli_session")
def test_policy_match_parses_cli_output(mock_open_cli):
    mock_session = mock_open_cli.return_value
    mock_session.send_command.return_value = "policy_id=12 action=deny"
    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=FakeHttpClient({}))
    rule = driver.test_policy_match("10.1.1.5", "157.240.1.1", 443, "tcp")
    assert rule.rule_id == "12"
    assert rule.action == "deny"


@patch.object(FortigateDriver, "open_cli_session")
def test_policy_match_no_match_returns_none(mock_open_cli):
    mock_session = mock_open_cli.return_value
    mock_session.send_command.return_value = "no policy found"
    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=FakeHttpClient({}))
    rule = driver.test_policy_match("10.1.1.5", "157.240.1.1", 443, "tcp")
    assert rule is None


def test_get_licenses_parses_bundle_dicts():
    fake = FakeHttpClient({
        "monitor/license/status": {"results": {
            "forticare": {"is_valid": True, "expiry_date": "2027-01-10"},
            "fortiguard_bundle": {"is_valid": True, "expiry_date": "2026-08-05"},
            "some_non_license_field": "not a dict, should be skipped",
        }},
    })
    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=fake)
    licenses = driver.get_licenses()
    assert len(licenses) == 2
    forticare = next(l for l in licenses if l.feature == "forticare")
    assert forticare.status == "active"
    assert forticare.expiry_date.year == 2027


def test_get_licenses_marks_invalid_as_expired():
    fake = FakeHttpClient({
        "monitor/license/status": {"results": {
            "fortiguard_av": {"is_valid": False, "expiry_date": "2024-01-01"},
        }},
    })
    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=fake)
    licenses = driver.get_licenses()
    assert licenses[0].status == "expired"


def test_get_running_config_returns_raw_text():
    class TextFakeHttpClient(FakeHttpClient):
        def get(self, url, headers=None, params=None, verify=None, timeout=None):
            if "config/backup" in url:
                class R:
                    status_code = 200
                    text = "#config-version=FGT-7.4\nconfig system global\nend\n"
                    def raise_for_status(self): pass
                return R()
            return super().get(url, headers, params, verify, timeout)

    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=TextFakeHttpClient({}))
    config = driver.get_running_config()
    assert "config system global" in config


def test_get_logs_defaults_to_traffic_endpoint():
    fake = FakeHttpClient({
        "log/disk/traffic/forward": {"results": [
            {"date": "2026-07-27", "time": "08:00:00", "level": "info", "srcip": "10.1.1.5", "dstip": "1.1.1.1",
             "action": "accept", "app": "HTTPS", "sentbyte": 5000, "rcvdbyte": 15000, "policyname": "allow-web"},
        ]},
    })
    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=fake)
    events = driver.get_logs({}, (None, None))
    assert len(events) == 1
    assert events[0].event_type.value == "traffic"
    assert events[0].app == "HTTPS"
    assert events[0].bytes_total == 20000
    assert events[0].matched_rule == "allow-web"


def test_get_logs_threat_type_hits_ips_endpoint():
    fake = FakeHttpClient({
        "log/disk/ips": {"results": [
            {"date": "2026-07-27", "time": "08:00:00", "level": "critical", "srcip": "10.1.1.5",
             "dstip": "45.33.32.156", "action": "dropped", "attack": "Trojan.Generic"},
        ]},
    })
    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=fake)
    events = driver.get_logs({"log_type": "threat"}, (None, None))
    assert len(events) == 1
    assert events[0].event_type.value == "threat"
    assert events[0].threat_name == "Trojan.Generic"


def test_get_logs_url_type_hits_webfilter_endpoint():
    fake = FakeHttpClient({
        "log/disk/webfilter/webfilter": {"results": [
            {"date": "2026-07-27", "time": "08:00:00", "level": "info", "srcip": "10.1.1.5",
             "action": "blocked", "url": "socialmedia.example.com", "catdesc": "Social Networking", "user": "vish"},
        ]},
    })
    driver = FortigateDriver(make_device(), {"api_key": "TOKEN"}, http_client=fake)
    events = driver.get_logs({"log_type": "url"}, (None, None))
    assert len(events) == 1
    assert events[0].event_type.value == "url"
    assert events[0].url == "socialmedia.example.com"
    assert events[0].category == "Social Networking"
    assert events[0].user == "vish"
