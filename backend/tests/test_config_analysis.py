from app.config_analysis import (
    parse_static_routes, parse_nat_rules, longest_prefix_match, find_nat_match,
)
from app.models import Vendor


PALOALTO_CONFIG = """<config>
  <devices><entry name="localhost.localdomain">
    <network>
      <virtual-router><entry name="default">
        <routing-table><ip><static-route>
          <entry name="default"><destination>0.0.0.0/0</destination>
            <nexthop><ip-address>203.0.113.1</ip-address></nexthop>
            <interface>ethernet1/1</interface></entry>
          <entry name="lan"><destination>10.1.0.0/16</destination>
            <nexthop><ip-address>10.0.0.254</ip-address></nexthop>
            <interface>ethernet1/2</interface></entry>
        </static-route></ip></routing-table>
      </entry></virtual-router>
    </network>
    <vsys><entry name="vsys1">
      <rulebase><nat><rules>
        <entry name="outbound-pat">
          <source><member>10.1.0.0/16</member></source>
          <destination><member>any</member></destination>
          <source-translation><dynamic-ip-and-port>
            <interface-address><interface>ethernet1/1</interface></interface-address>
          </dynamic-ip-and-port></source-translation>
        </entry>
        <entry name="dnat-web">
          <source><member>any</member></source>
          <destination><member>203.0.113.1</member></destination>
          <destination-translation><translated-address>10.1.1.50</translated-address></destination-translation>
        </entry>
      </rules></nat></rulebase>
    </entry></vsys>
  </entry></devices>
</config>"""

CISCO_CONFIG = """
hostname edge-router-01
!
ip route 0.0.0.0 0.0.0.0 198.51.100.1
ip route 10.2.0.0 255.255.0.0 10.0.0.254 GigabitEthernet0/1
ip nat inside source static 10.1.1.50 203.0.113.50
ip nat inside source list 10 interface GigabitEthernet0/0 overload
!
"""

FORTIGATE_CONFIG = """
config router static
    edit 1
        set dst 0.0.0.0 0.0.0.0
        set gateway 192.0.2.1
        set device "wan1"
    next
    edit 2
        set dst 10.3.0.0 255.255.0.0
        set gateway 10.0.0.254
        set device "internal"
    next
end
"""


def test_paloalto_static_route_parsing():
    routes = parse_static_routes(Vendor.PALOALTO, "fw-1", PALOALTO_CONFIG)
    assert len(routes) == 2
    lan_route = next(r for r in routes if r.destination_subnet == "10.1.0.0/16")
    assert lan_route.next_hop == "10.0.0.254"
    assert lan_route.egress_interface == "ethernet1/2"


def test_paloalto_nat_parsing_distinguishes_source_and_destination_nat():
    rules = parse_nat_rules(Vendor.PALOALTO, "fw-1", PALOALTO_CONFIG)
    assert len(rules) == 2
    dnat = next(r for r in rules if r.name == "dnat-web")
    assert dnat.nat_type == "destination"
    assert dnat.translated_address == "10.1.1.50"
    snat = next(r for r in rules if r.name == "outbound-pat")
    assert snat.nat_type == "source"
    assert "interface" in snat.translated_address.lower()


def test_cisco_static_route_parsing_handles_default_and_subnet():
    routes = parse_static_routes(Vendor.CISCO_IOS, "rtr-1", CISCO_CONFIG)
    assert len(routes) == 2
    default = next(r for r in routes if r.destination_subnet == "0.0.0.0/0")
    assert default.next_hop == "198.51.100.1"
    subnet_route = next(r for r in routes if r.destination_subnet == "10.2.0.0/16")
    assert subnet_route.egress_interface == "GigabitEthernet0/1"


def test_cisco_nat_parsing_static_and_overload():
    rules = parse_nat_rules(Vendor.CISCO_IOS, "rtr-1", CISCO_CONFIG)
    static_rule = next(r for r in rules if r.name == "static-inside-source")
    assert static_rule.source == "10.1.1.50"
    assert static_rule.translated_address == "203.0.113.50"
    pat_rule = next(r for r in rules if "pat-via" in r.name)
    assert "GigabitEthernet0/0" in pat_rule.translated_address


def test_fortigate_static_route_parsing():
    routes = parse_static_routes(Vendor.FORTIGATE, "fw-2", FORTIGATE_CONFIG)
    assert len(routes) == 2
    internal = next(r for r in routes if r.destination_subnet == "10.3.0.0/16")
    assert internal.next_hop == "10.0.0.254"
    assert internal.egress_interface == "internal"


def test_fortigate_nat_parsing_returns_empty_not_fabricated():
    # NAT parsing isn't implemented for Fortigate yet -- must return
    # an honest empty list, never a guessed rule.
    assert parse_nat_rules(Vendor.FORTIGATE, "fw-2", FORTIGATE_CONFIG) == []


def test_longest_prefix_match_picks_most_specific_route():
    routes = parse_static_routes(Vendor.PALOALTO, "fw-1", PALOALTO_CONFIG)
    match = longest_prefix_match(routes, "10.1.5.20")
    assert match.destination_subnet == "10.1.0.0/16"

    default_match = longest_prefix_match(routes, "8.8.8.8")
    assert default_match.destination_subnet == "0.0.0.0/0"


def test_longest_prefix_match_returns_none_for_invalid_ip():
    routes = parse_static_routes(Vendor.CISCO_IOS, "rtr-1", CISCO_CONFIG)
    assert longest_prefix_match(routes, "not-an-ip") is None


def test_find_nat_match_respects_source_and_destination():
    rules = parse_nat_rules(Vendor.PALOALTO, "fw-1", PALOALTO_CONFIG)
    match = find_nat_match(rules, "10.1.1.5", "8.8.8.8")
    assert match.name == "outbound-pat"

    dnat_match = find_nat_match(rules, "1.2.3.4", "203.0.113.1")
    assert dnat_match.name == "dnat-web"


def test_find_nat_match_returns_none_when_nothing_applies():
    rules = parse_nat_rules(Vendor.CISCO_IOS, "rtr-1", CISCO_CONFIG)
    assert find_nat_match(rules, "192.168.99.99", "1.1.1.1") is None
