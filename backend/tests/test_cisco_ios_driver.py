from app.models import Device, Vendor, DeviceType
from app.drivers.cisco_ios import CiscoIOSRouterDriver, CiscoIOSSwitchDriver


class FakeCiscoSession:
    """Scripts canned `show` command output so tests don't need a real
    SSH connection. Keyed by a distinctive substring of the command."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.commands_sent = []

    def send_command(self, command):
        self.commands_sent.append(command)
        for key, output in self.responses.items():
            if key in command:
                return output
        return ""

    def close(self):
        pass


SHOW_VERSION = """Cisco IOS XE Software, Version 17.09.04
Cisco IOS Software [Cupertino], ISR software (X86_64_LINUX_IOSD-UNIVERSALK9-M), Version 17.9.4a
cisco C8000V (VXE) processor (revision VXE) with 1869697K/3075K bytes of memory.
Processor board ID 9ABC1234XYZ
router-edge-1 uptime is 2 weeks, 3 days, 4 hours, 12 minutes
"""

SHOW_IP_INT_BRIEF = """Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet1       10.0.0.1        YES manual up                    up
GigabitEthernet2       unassigned      YES unset  administratively down down
"""

SHOW_IP_ROUTE = """Routing entry for 157.240.0.0/16
  Known via "ospf 1", distance 110, metric 20
  Routing Descriptor Blocks:
  * 10.0.0.254, from 10.0.0.254, via GigabitEthernet1
"""

SHOW_CDP_NEIGHBORS = """-------------------------
Device ID: core-switch-1.example.com
Entry address(es):
  IP address: 10.0.0.5
Platform: cisco WS-C3850,  Capabilities: Switch IGMP
Interface: GigabitEthernet1,  Port ID (outgoing port): GigabitEthernet0/1
-------------------------
"""

SHOW_MAC_TABLE = """          Mac Address Table
-------------------------------------------
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
  10    aabb.ccdd.eeff    DYNAMIC     Gi0/5
"""

SHOW_IP_ARP = """Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  10.1.1.5                12   aabb.ccdd.eeff  ARPA   Vlan10
"""


SHOW_INTERFACES = """GigabitEthernet1 is up, line protocol is up
  Hardware is CSR vNIC, address is 5254.0012.3400 (bia 5254.0012.3400)
  5 minute input rate 1200000 bits/sec, 100 packets/sec
  5 minute output rate 900000 bits/sec, 80 packets/sec
     123456789 bytes input, 45 no buffer
     987654321 bytes output, 0 underruns
GigabitEthernet2 is administratively down, line protocol is down
  Hardware is CSR vNIC, address is 5254.0012.3401 (bia 5254.0012.3401)
     0 bytes input
     0 bytes output
"""


SHOW_LICENSE_STATUS = """Smart Licensing is ENABLED

Registration:
  Status: REGISTERED
  Smart Account: Example Corp
  Export-Controlled Functionality: Allowed

License Authorization:
  Status: AUTHORIZED
"""

SHOW_LICENSE_SUMMARY = """Smart Licensing is ENABLED

License Usage:
  License                Entitlement tag                  Count Status
  -----------------------------------------------------------------------
  network-advantage      (ISR_1100-4G:network-advantage)      1  IN USE
  dna-advantage          (ISR_1100-4G:dna-advantage)           1  IN USE
"""


def make_router():
    device = Device(device_id="rt-1", hostname="router-edge-1", mgmt_ip="10.0.0.1",
                     vendor=Vendor.CISCO_IOS, device_type=DeviceType.ROUTER)
    session = FakeCiscoSession({
        "show version": SHOW_VERSION,
        "show ip interface brief": SHOW_IP_INT_BRIEF,
        "show interfaces": SHOW_INTERFACES,
        "show ip route 157.240.1.1": SHOW_IP_ROUTE,
        "show cdp neighbors detail": SHOW_CDP_NEIGHBORS,
        "show license status": SHOW_LICENSE_STATUS,
        "show license summary": SHOW_LICENSE_SUMMARY,
        "show running-config": "Building configuration...\n\nhostname router-edge-1\n!\ninterface GigabitEthernet1\n ip address 10.0.0.1 255.255.255.0\n!\nend\n",
    })
    driver = CiscoIOSRouterDriver(device, {"username": "admin", "password": "x"},
                                   cli_session_factory=lambda: session)
    return driver


def make_switch():
    device = Device(device_id="sw-1", hostname="core-switch-1", mgmt_ip="10.0.0.5",
                     vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    session = FakeCiscoSession({
        "show version": SHOW_VERSION,
        "show ip interface brief": SHOW_IP_INT_BRIEF,
        "show mac address-table": SHOW_MAC_TABLE,
        "show ip arp": SHOW_IP_ARP,
        "show license status": SHOW_LICENSE_STATUS,
        "show license summary": SHOW_LICENSE_SUMMARY,
    })
    driver = CiscoIOSSwitchDriver(device, {"username": "admin", "password": "x"},
                                   cli_session_factory=lambda: session)
    return driver


def test_router_get_facts_parses_show_version():
    driver = make_router()
    device = driver.get_facts()
    assert device.model == "C8000V"
    assert device.serial_number == "9ABC1234XYZ"
    assert device.hostname == "router-edge-1"


def test_router_get_interfaces_parses_status():
    driver = make_router()
    interfaces = driver.get_interfaces()
    by_name = {i.if_name: i for i in interfaces}
    assert by_name["GigabitEthernet1"].status == "up"
    assert by_name["GigabitEthernet1"].ip_address == "10.0.0.1"
    assert by_name["GigabitEthernet2"].status == "down"


def test_router_get_interfaces_parses_mac_and_counters():
    driver = make_router()
    interfaces = driver.get_interfaces()
    by_name = {i.if_name: i for i in interfaces}
    gi1 = by_name["GigabitEthernet1"]
    assert gi1.mac_address == "5254.0012.3400"
    assert gi1.rx_bytes == 123456789
    assert gi1.tx_bytes == 987654321
    assert gi1.admin_status == "enabled"
    gi2 = by_name["GigabitEthernet2"]
    assert gi2.admin_status == "disabled"


def test_router_get_route_finds_next_hop_and_protocol():
    driver = make_router()
    routes = driver.get_route("157.240.1.1")
    assert len(routes) == 1
    assert routes[0].next_hop == "10.0.0.254"
    assert routes[0].protocol == "ospf"


def test_router_get_neighbors_parses_cdp():
    driver = make_router()
    neighbors = driver.get_neighbors()
    assert len(neighbors) == 1
    assert neighbors[0].neighbor_hostname == "core-switch-1.example.com"
    assert neighbors[0].local_interface == "GigabitEthernet1"
    assert neighbors[0].neighbor_interface == "GigabitEthernet0/1"
    assert neighbors[0].neighbor_mgmt_ip == "10.0.0.5"


def test_router_get_licenses_parses_smart_licensing_entitlements():
    driver = make_router()
    licenses = driver.get_licenses()
    assert len(licenses) == 2
    features = {l.feature for l in licenses}
    assert features == {"network-advantage", "dna-advantage"}
    for l in licenses:
        assert l.status == "active"
        assert l.expiry_date is None  # honestly not available from this command
        assert "registered: True" in l.description


SHOW_IP_CACHE_FLOW = """IP packet size distribution (25 total packets):
   1-32   64   96  128  160  192  224  256  288  320  352  384  416  448  480
   .000  .200 .000 .000 .000 .000 .000 .000 .000 .000 .000 .000 .000 .000 .000

IP Flow Switching Cache, 278544 bytes

SrcIf         SrcIPaddress    DstIf         DstIPaddress    Pr SrcP DstP  Pkts
Gi0/1         10.1.1.5        Gi0/2         157.240.1.1     06 C350 01BB    10
Gi0/1         10.1.1.9        Gi0/2         8.8.8.8         11 C351 0035     3
"""


def test_router_get_sessions_parses_netflow_cache_with_hex_decoding():
    device = Device(device_id="rt-1", hostname="router-edge-1", mgmt_ip="10.0.0.1",
                     vendor=Vendor.CISCO_IOS, device_type=DeviceType.ROUTER)
    session = FakeCiscoSession({"show ip cache flow": SHOW_IP_CACHE_FLOW})
    driver = CiscoIOSRouterDriver(device, {"username": "admin", "password": "x"},
                                   cli_session_factory=lambda: session)
    sessions = driver.get_sessions()
    assert len(sessions) == 2

    tcp_flow = next(s for s in sessions if s.protocol == "tcp")
    assert tcp_flow.src_ip == "10.1.1.5"
    assert tcp_flow.dst_ip == "157.240.1.1"
    assert tcp_flow.src_port == 0xC350  # 50000
    assert tcp_flow.dst_port == 0x01BB  # 443
    assert tcp_flow.app is None

    udp_flow = next(s for s in sessions if s.protocol == "udp")
    assert udp_flow.dst_port == 0x0035  # 53 (DNS)


def test_router_get_sessions_filters_by_src_and_dst_ip():
    device = Device(device_id="rt-1", hostname="router-edge-1", mgmt_ip="10.0.0.1",
                     vendor=Vendor.CISCO_IOS, device_type=DeviceType.ROUTER)
    session = FakeCiscoSession({"show ip cache flow": SHOW_IP_CACHE_FLOW})
    driver = CiscoIOSRouterDriver(device, {"username": "admin", "password": "x"},
                                   cli_session_factory=lambda: session)
    sessions = driver.get_sessions(src_ip="10.1.1.5")
    assert len(sessions) == 1
    assert sessions[0].dst_ip == "157.240.1.1"


def test_switch_get_arp_mac_table_joins_mac_and_arp():
    driver = make_switch()
    entries = driver.get_arp_mac_table()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.mac_address == "aabb.ccdd.eeff"
    assert entry.ip_address == "10.1.1.5"
    assert entry.vlan_id == 10
    assert entry.interface == "Gi0/5"


def test_switch_get_licenses_also_supported():
    driver = make_switch()
    licenses = driver.get_licenses()
    assert len(licenses) == 2


def test_router_get_running_config_returns_raw_text():
    driver = make_router()
    config = driver.get_running_config()
    assert "hostname router-edge-1" in config
    assert "interface GigabitEthernet1" in config
