"""Real, config-file-based misconfiguration checks -- run automatically
every time a device's config is parsed (see config_backup_hooks.py),
so a problem shows up the moment it's introduced rather than only when
someone happens to run Troubleshooting against the affected flow.

Deliberately scoped to what a static config dump can actually tell
you: routing and NAT structure. Latency and packet drops need live
interface counters (Interface.drops/errors, already collected by
get_interfaces -- see the "still not covered" note in troubleshooting
docs), not config text, so this module doesn't guess at those.
"""
from __future__ import annotations

from app.models import RouteEntry
from app.config_analysis import NatRule


def analyze_routes(device_id: str, routes: list[RouteEntry]) -> list[dict]:
    findings: list[dict] = []

    if not routes:
        findings.append({
            "severity": "info", "category": "routing",
            "message": "No static routes found in the downloaded configuration.",
        })
        return findings

    if not any(r.destination_subnet in ("0.0.0.0/0",) for r in routes):
        findings.append({
            "severity": "warning", "category": "routing",
            "message": "No default route configured -- traffic to any destination outside the known static routes will be dropped.",
        })

    # Same destination subnet configured twice with a different next
    # hop is ambiguous -- most platforms pick one deterministically,
    # but it's rarely intentional and worth flagging.
    seen: dict[str, str] = {}
    for route in routes:
        prior = seen.get(route.destination_subnet)
        if prior is not None and prior != route.next_hop:
            findings.append({
                "severity": "warning", "category": "routing",
                "message": f"Conflicting static routes for {route.destination_subnet}: next-hop {prior} vs {route.next_hop}.",
            })
        seen[route.destination_subnet] = route.next_hop

    # A route with no next hop and no egress interface can't actually
    # forward anything.
    for route in routes:
        if route.next_hop in ("", "(none)") and not route.egress_interface:
            findings.append({
                "severity": "warning", "category": "routing",
                "message": f"Route to {route.destination_subnet} has neither a next hop nor an egress interface -- it can't forward traffic.",
            })

    return findings


def analyze_nat(device_id: str, nat_rules: list[NatRule]) -> list[dict]:
    findings: list[dict] = []
    for rule in nat_rules:
        if not rule.translated_address:
            findings.append({
                "severity": "warning", "category": "nat",
                "message": f"NAT rule '{rule.name}' has no translated address configured.",
            })
    return findings


def analyze(device_id: str, routes: list[RouteEntry], nat_rules: list[NatRule]) -> list[dict]:
    return analyze_routes(device_id, routes) + analyze_nat(device_id, nat_rules)
