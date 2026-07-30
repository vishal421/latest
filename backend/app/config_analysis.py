"""Parses the config text InfraOS already downloads and stores per
device (ConfigBackup.content -- see api/config_backups.py) for the two
things Troubleshooting needs from it: static routes (for longest-
prefix-match routing analysis) and NAT rules. This is deliberately
*not* a live driver call -- the whole point is to build routing/NAT
analysis on top of data already collected, not add another live
round-trip per troubleshooting run.

Each vendor stores config in a genuinely different format (PAN-OS:
XML: Cisco IOS: plain `show running-config` text; FortiOS: CLI-style
config blocks), so there's one real parser per vendor below. Where a
vendor's format for something isn't implemented, the parser returns
an empty list -- never a guessed/fabricated entry.
"""
from __future__ import annotations

import ipaddress
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from app.models import RouteEntry, Vendor


@dataclass
class NatRule:
    device_id: str
    name: str
    source: str            # matches PolicyRule-style loose zone/IP text, "any" if unspecified
    destination: str
    translated_address: str
    nat_type: str = "source"   # source | destination


def _cidr_from_mask(dotted_mask: str) -> int:
    try:
        return sum(bin(int(o)).count("1") for o in dotted_mask.split("."))
    except (ValueError, AttributeError):
        return 32


def parse_static_routes(vendor: Vendor, device_id: str, config_text: str) -> list[RouteEntry]:
    """Real per-vendor parsing of static routes out of the device's
    own downloaded config. Dynamic-protocol routes (OSPF/BGP) aren't
    visible in a static config dump the same way, so this only ever
    returns what's genuinely configured as `static` -- it doesn't
    infer or estimate anything a routing protocol would have
    installed at runtime."""
    if not config_text:
        return []
    if vendor == Vendor.PALOALTO:
        return _parse_paloalto_routes(device_id, config_text)
    if vendor == Vendor.CISCO_IOS:
        return _parse_cisco_routes(device_id, config_text)
    if vendor == Vendor.FORTIGATE:
        return _parse_fortigate_routes(device_id, config_text)
    return []


def parse_nat_rules(vendor: Vendor, device_id: str, config_text: str) -> list[NatRule]:
    """Real per-vendor NAT rule parsing. Fortigate's NAT model (policy-
    based NAT + separate VIP objects) isn't implemented yet -- rather
    than approximate it and risk a wrong answer, this honestly returns
    an empty list for that vendor until it's built."""
    if not config_text:
        return []
    if vendor == Vendor.PALOALTO:
        return _parse_paloalto_nat(device_id, config_text)
    if vendor == Vendor.CISCO_IOS:
        return _parse_cisco_nat(device_id, config_text)
    return []


def _parse_paloalto_routes(device_id: str, config_text: str) -> list[RouteEntry]:
    try:
        root = ET.fromstring(config_text)
    except ET.ParseError:
        return []
    routes = []
    # <virtual-router><entry name="..."><routing-table><ip><static-route><entry name="...">
    for vr in root.findall(".//virtual-router/entry"):
        for route_entry in vr.findall(".//static-route/entry"):
            destination = route_entry.findtext("destination", default="")
            next_hop = route_entry.findtext("nexthop/ip-address", default="") or route_entry.findtext("nexthop/next-vr", default="")
            interface = route_entry.findtext("interface", default="")
            if not destination:
                continue
            routes.append(RouteEntry(
                device_id=device_id, destination_subnet=destination,
                next_hop=next_hop or "(none)", egress_interface=interface, protocol="static",
            ))
    return routes


def _parse_paloalto_nat(device_id: str, config_text: str) -> list[NatRule]:
    try:
        root = ET.fromstring(config_text)
    except ET.ParseError:
        return []
    rules = []
    for entry in root.findall(".//rulebase/nat/rules/entry"):
        name = entry.get("name", "unknown")
        source = entry.findtext("source/member", default="any")
        destination = entry.findtext("destination/member", default="any")
        src_translated = entry.findtext(".//source-translation//translated-address", default="")
        dst_translated = entry.findtext(".//destination-translation/translated-address", default="")
        if dst_translated:
            rules.append(NatRule(device_id=device_id, name=name, source=source, destination=destination,
                                  translated_address=dst_translated, nat_type="destination"))
        elif src_translated:
            rules.append(NatRule(device_id=device_id, name=name, source=source, destination=destination,
                                  translated_address=src_translated, nat_type="source"))
        elif entry.find(".//source-translation/dynamic-ip-and-port") is not None:
            rules.append(NatRule(device_id=device_id, name=name, source=source, destination=destination,
                                  translated_address="dynamic-ip-and-port (interface address)", nat_type="source"))
    return rules


def _parse_cisco_routes(device_id: str, config_text: str) -> list[RouteEntry]:
    routes = []
    # ip route <dest> <mask> <next-hop-or-interface> [interface]
    for line in config_text.splitlines():
        m = re.match(r"^ip route\s+([\d.]+)\s+([\d.]+)\s+(\S+)(?:\s+(\S+))?", line.strip())
        if not m:
            continue
        dest, mask, hop_or_if, maybe_if = m.groups()
        prefix_len = _cidr_from_mask(mask)
        # Cisco allows "ip route <dst> <mask> <interface>" (no next-hop IP)
        # for point-to-point links -- detect that case.
        is_ip = re.match(r"^\d+\.\d+\.\d+\.\d+$", hop_or_if)
        next_hop = hop_or_if if is_ip else "(directly connected)"
        egress_if = maybe_if or (hop_or_if if not is_ip else "")
        routes.append(RouteEntry(
            device_id=device_id, destination_subnet=f"{dest}/{prefix_len}",
            next_hop=next_hop, egress_interface=egress_if, protocol="static",
        ))
    return routes


def _parse_cisco_nat(device_id: str, config_text: str) -> list[NatRule]:
    rules = []
    for line in config_text.splitlines():
        line = line.strip()
        # ip nat inside source static <local-ip> <global-ip>
        m = re.match(r"^ip nat inside source static\s+([\d.]+)\s+([\d.]+)", line)
        if m:
            local_ip, global_ip = m.groups()
            rules.append(NatRule(device_id=device_id, name="static-inside-source",
                                  source=local_ip, destination="any",
                                  translated_address=global_ip, nat_type="source"))
            continue
        # ip nat inside source list <acl> interface <if> overload
        m = re.match(r"^ip nat inside source list\s+(\S+)\s+interface\s+(\S+)", line)
        if m:
            acl, iface = m.groups()
            rules.append(NatRule(device_id=device_id, name=f"pat-via-{iface}",
                                  source=f"(acl {acl})", destination="any",
                                  translated_address=f"interface {iface} address (PAT)", nat_type="source"))
    return rules


def _parse_fortigate_routes(device_id: str, config_text: str) -> list[RouteEntry]:
    routes = []
    in_static_block = False
    current: dict = {}
    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if line == "config router static":
            in_static_block = True
            continue
        if not in_static_block:
            continue
        if line == "end":
            in_static_block = False
            continue
        if line.startswith("edit "):
            current = {}
            continue
        if line.startswith("set dst "):
            parts = line.split()
            if len(parts) >= 4:
                current["dst"] = parts[2]
                current["mask"] = parts[3]
        elif line.startswith("set gateway "):
            current["gateway"] = line.split()[-1]
        elif line.startswith("set device "):
            current["device"] = line.split()[-1].strip('"')
        elif line == "next" and "dst" in current:
            prefix_len = _cidr_from_mask(current.get("mask", "255.255.255.255"))
            routes.append(RouteEntry(
                device_id=device_id,
                destination_subnet=f"{current['dst']}/{prefix_len}",
                next_hop=current.get("gateway", "(none)"),
                egress_interface=current.get("device", ""),
                protocol="static",
            ))
            current = {}
    return routes


def longest_prefix_match(routes: list[RouteEntry], dst_ip: str) -> Optional[RouteEntry]:
    """Standard longest-prefix-match: among every static route whose
    subnet actually contains dst_ip, the one with the most specific
    (highest prefix length) subnet wins -- same rule every real router
    uses to pick a route. Malformed subnets in the config are skipped
    rather than raising, since a downloaded config occasionally has a
    partially-applied entry."""
    try:
        target = ipaddress.ip_address(dst_ip)
    except ValueError:
        return None
    best: Optional[RouteEntry] = None
    best_prefix = -1
    for route in routes:
        try:
            network = ipaddress.ip_network(route.destination_subnet, strict=False)
        except ValueError:
            continue
        if target in network and network.prefixlen > best_prefix:
            best = route
            best_prefix = network.prefixlen
    return best


def find_nat_match(nat_rules: list[NatRule], src_ip: str, dst_ip: str) -> Optional[NatRule]:
    """Best-effort NAT match: a rule applies if its configured source/
    destination is 'any' or actually contains the IP in question. Real
    PAN-OS/IOS NAT rule matching also considers zones and rule order,
    which isn't visible from a static config dump alone -- so this is
    reported as 'a NAT rule that would apply', not a guaranteed final
    verdict, and the troubleshooting output says exactly that."""
    def _matches(field: str, ip: str) -> bool:
        if field in ("any", "", "0.0.0.0/0"):
            return True
        try:
            return ipaddress.ip_address(ip) in ipaddress.ip_network(field, strict=False)
        except ValueError:
            return field == ip
    for rule in nat_rules:
        if _matches(rule.source, src_ip) and _matches(rule.destination, dst_ip):
            return rule
    return None
