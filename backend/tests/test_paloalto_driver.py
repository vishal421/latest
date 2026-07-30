from app.models import Device, Vendor, DeviceType
from app.drivers.paloalto import PaloAltoDriver


class FakeResponse:
    def __init__(self, text="", json_data=None, status=200):
        self.text = text
        self._json = json_data or {}
        self.status_code = status

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class FakeHttpClient:
    """Returns canned XML responses keyed by the `type`/`cmd` query params,
    so each test can script exactly the PAN-OS response it wants.

    For `type=op` calls specifically, routes by a substring of `cmd` so
    a single test can script different responses for `show interface
    all` vs. `show counter interface all` vs. other op-commands that
    share the same `type` value. Falls back to the plain `op` key for
    tests that only care about one op-command.
    """

    def __init__(self, responses: dict):
        self.responses = responses
        self.calls = []

    def get(self, url, params=None, verify=None, timeout=None):
        self.calls.append(params)
        key = params.get("type")
        if key == "op":
            cmd = params.get("cmd", "")
            if "counter" in cmd and "op_counter" in self.responses:
                return FakeResponse(text=self.responses["op_counter"])
            if "interface" in cmd and "op_interface" in self.responses:
                return FakeResponse(text=self.responses["op_interface"])
        return FakeResponse(text=self.responses.get(key, "<response></response>"))


def make_device():
    return Device(
        device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
        vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL,
    )


def test_connect_extracts_api_key():
    fake = FakeHttpClient({"keygen": "<response><result><key>ABC123</key></result></response>"})
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    driver.connect()
    assert driver._api_key == "ABC123"


def test_get_interfaces_merges_hw_mac_and_byte_counters():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op_interface": """<response><result>
            <ifnet>
                <entry><name>ethernet1/1</name><ip>10.10.0.1/24</ip><state>up</state></entry>
                <entry><name>ethernet1/2</name><ip>N/A</ip><state>down</state></entry>
            </ifnet>
            <hw>
                <entry><name>ethernet1/1</name><mac>aa:bb:cc:dd:ee:01</mac><state>up</state></entry>
            </hw>
        </result></response>""",
        "op_counter": """<response><result><ifnet>
            <entry><name>ethernet1/1</name><ibytes>500000</ibytes><obytes>250000</obytes></entry>
        </ifnet></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    interfaces = driver.get_interfaces()
    eth1 = next(i for i in interfaces if i.if_name == "ethernet1/1")
    assert eth1.oper_status == "up"
    assert eth1.admin_status == "enabled"
    assert eth1.mac_address == "aa:bb:cc:dd:ee:01"
    assert eth1.tx_bytes == 250000
    assert eth1.rx_bytes == 500000

    # ethernet1/2 has no <hw> entry at all -- best-effort read as
    # administratively disabled, and no counters available for it.
    eth2 = next(i for i in interfaces if i.if_name == "ethernet1/2")
    assert eth2.admin_status == "disabled"
    assert eth2.tx_bytes is None
    assert eth2.rx_bytes is None


def test_get_interfaces_subinterface_inherits_parent_mac_not_admin_state():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op_interface": """<response><result>
            <ifnet>
                <entry><name>ethernet1/1.100</name><ip>10.20.0.1/24</ip><state>up</state></entry>
            </ifnet>
            <hw>
                <entry><name>ethernet1/1</name><mac>aa:bb:cc:dd:ee:01</mac><state>up</state></entry>
            </hw>
        </result></response>""",
        "op_counter": "<response><result><ifnet></ifnet></result></response>",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    sub = driver.get_interfaces()[0]
    assert sub.mac_address == "aa:bb:cc:dd:ee:01"  # inherited from parent physical interface
    assert sub.admin_status == "unknown"  # sub-interfaces have no independent admin-disable in PAN-OS


def test_get_interfaces_counter_call_failure_degrades_gracefully():
    """If `show counter interface all` isn't supported or errors, interface
    listing should still work -- counters just come back None, not an
    exception that breaks the whole poll."""
    class RaisingOnCounterClient(FakeHttpClient):
        def get(self, url, params=None, verify=None, timeout=None):
            if params.get("type") == "op" and "counter" in params.get("cmd", ""):
                raise ConnectionError("device doesn't support this op-command")
            return super().get(url, params=params, verify=verify, timeout=timeout)

    fake = RaisingOnCounterClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op_interface": """<response><result>
            <ifnet><entry><name>ethernet1/1</name><ip>10.10.0.1/24</ip><state>up</state></entry></ifnet>
            <hw><entry><name>ethernet1/1</name><mac>aa:bb:cc:dd:ee:01</mac><state>up</state></entry></hw>
        </result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    interfaces = driver.get_interfaces()
    assert len(interfaces) == 1
    assert interfaces[0].mac_address == "aa:bb:cc:dd:ee:01"
    assert interfaces[0].tx_bytes is None
    assert interfaces[0].rx_bytes is None


def test_get_facts_parses_system_info():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op": """<response><result><system>
            <hostname>fw1</hostname><model>PA-820</model>
            <sw-version>11.1.2</sw-version><serial>001122334455</serial>
        </system></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    device = driver.get_facts()
    assert device.model == "PA-820"
    assert device.os_version == "11.1.2"
    assert device.serial_number == "001122334455"


def test_test_policy_match_allow():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op": """<response><result><rules>
            <entry name="allow-web"><action>allow</action></entry>
        </rules></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    rule = driver.test_policy_match("10.1.1.5", "157.240.1.1", 443, "tcp")
    assert rule.action == "allow"
    assert rule.name == "allow-web"


def test_test_policy_match_deny_returns_deny_action():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op": """<response><result><rules>
            <entry name="block-social-media"><action>deny</action></entry>
        </rules></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    rule = driver.test_policy_match("10.1.1.5", "157.240.1.1", 443, "tcp")
    assert rule.action == "deny"
    assert rule.name == "block-social-media"


def test_test_policy_match_no_rule_returns_none():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op": "<response><result><rules></rules></result></response>",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    rule = driver.test_policy_match("10.1.1.5", "157.240.1.1", 443, "tcp")
    assert rule is None


def test_health_check_parses_real_response_shape():
    # This is PAN-OS's actual response shape for `show system resources`
    # -- the raw `top` text sits directly in <result>. There's no
    # <resources> element anywhere in the response (that tag only
    # exists in the request); a driver that looks for one there will
    # always come back empty.
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op": """<response><result>
top - 14:32:05 up 40 days,  3:12,  0 users,  load average: 0.42, 0.38, 0.35
Tasks: 210 total,   1 running, 209 sleeping,   0 stopped,   0 zombie
%Cpu(s): 12.5 us,  3.1 sy,  0.0 ni, 84.0 id,  0.2 wa,  0.0 hi,  0.2 si,  0.0 st
KiB Mem : 16330000 total,  4200000 free,  9800000 used,  61.5% used
</result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    snapshot = driver.health_check()
    assert snapshot.cpu_pct == 12.5
    assert snapshot.memory_pct == 61.5


def test_get_licenses_parses_real_response_shape():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op": """<response><result><licenses>
            <entry>
                <feature>Threat Prevention</feature>
                <description>Threat Prevention License</description>
                <expires>January 01, 2027</expires>
                <expired>no</expired>
            </entry>
            <entry>
                <feature>PAN-DB URL Filtering</feature>
                <description>Palo Alto Networks URL Filtering License</description>
                <expires>March 15, 2026</expires>
                <expired>no</expired>
            </entry>
        </licenses></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    licenses = driver.get_licenses()
    assert len(licenses) == 2
    tp = next(l for l in licenses if l.feature == "Threat Prevention")
    assert tp.status == "active"
    assert tp.expiry_date.year == 2027 and tp.expiry_date.month == 1


def test_get_licenses_marks_expired_license():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op": """<response><result><licenses>
            <entry><feature>Old Add-on</feature><expires>January 01, 2020</expires><expired>yes</expired></entry>
        </licenses></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    licenses = driver.get_licenses()
    assert licenses[0].status == "expired"


def test_get_licenses_handles_no_expiry_as_none_not_error():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op": """<response><result><licenses>
            <entry><feature>Support</feature><expired>no</expired></entry>
        </licenses></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    licenses = driver.get_licenses()
    assert licenses[0].expiry_date is None
    assert licenses[0].status == "active"


def test_get_running_config_returns_config_xml():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "op": """<response><result><config version="11.1.0">
            <devices><entry name="localhost.localdomain"><vsys><entry name="vsys1">
                <zone><entry name="trust"/></zone>
            </entry></vsys></entry></devices>
        </config></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    config = driver.get_running_config()
    assert "zone" in config
    assert "trust" in config


def test_get_logs_defaults_to_traffic_type():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "log": """<response><result><logs>
            <entry><receive_time>2026/07/27 08:00:00</receive_time><severity>info</severity>
                <src>10.1.1.5</src><dst>1.1.1.1</dst><action>allow</action><app>ssl</app>
                <bytes>123456</bytes><rule>allow-web</rule></entry>
        </logs></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    events = driver.get_logs({}, (None, None))
    assert len(events) == 1
    assert events[0].event_type.value == "traffic"
    assert events[0].src_ip == "10.1.1.5"
    assert events[0].app == "ssl"
    assert events[0].bytes_total == 123456
    assert events[0].matched_rule == "allow-web"


def test_get_logs_threat_type_parses_threat_name():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "log": """<response><result><logs>
            <entry><receive_time>2026/07/27 08:00:00</receive_time><severity>critical</severity>
                <src>10.1.1.5</src><dst>45.33.32.156</dst><action>reset-both</action>
                <threatid>Trojan.Generic</threatid></entry>
        </logs></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    events = driver.get_logs({"log_type": "threat"}, (None, None))
    assert len(events) == 1
    assert events[0].event_type.value == "threat"
    assert events[0].threat_name == "Trojan.Generic"


def test_get_logs_url_type_parses_url_and_category():
    fake = FakeHttpClient({
        "keygen": "<response><result><key>KEY</key></result></response>",
        "log": """<response><result><logs>
            <entry><receive_time>2026/07/27 08:00:00</receive_time><severity>info</severity>
                <src>10.1.1.5</src><action>deny</action>
                <url>socialmedia.example.com</url><category>social-networking</category>
                <srcuser>vish</srcuser></entry>
        </logs></result></response>""",
    })
    driver = PaloAltoDriver(make_device(), {"username": "admin", "password": "x"}, http_client=fake)
    events = driver.get_logs({"log_type": "url"}, (None, None))
    assert len(events) == 1
    assert events[0].event_type.value == "url"
    assert events[0].url == "socialmedia.example.com"
    assert events[0].category == "social-networking"
    assert events[0].user == "vish"
