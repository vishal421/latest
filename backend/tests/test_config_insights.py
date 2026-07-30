from app.models import RouteEntry
from app.config_analysis import NatRule
from app.config_insights import analyze_routes, analyze_nat, analyze


def test_flags_missing_default_route():
    routes = [RouteEntry(device_id="fw-1", destination_subnet="10.1.0.0/16", next_hop="10.0.0.254", egress_interface="eth1")]
    findings = analyze_routes("fw-1", routes)
    assert any("default route" in f["message"].lower() for f in findings)


def test_no_finding_when_default_route_present():
    routes = [RouteEntry(device_id="fw-1", destination_subnet="0.0.0.0/0", next_hop="203.0.113.1", egress_interface="eth1")]
    findings = analyze_routes("fw-1", routes)
    assert not any("default route" in f["message"].lower() for f in findings)


def test_flags_conflicting_routes():
    routes = [
        RouteEntry(device_id="fw-1", destination_subnet="10.2.0.0/16", next_hop="10.0.0.1", egress_interface="eth1"),
        RouteEntry(device_id="fw-1", destination_subnet="10.2.0.0/16", next_hop="10.0.0.2", egress_interface="eth2"),
        RouteEntry(device_id="fw-1", destination_subnet="0.0.0.0/0", next_hop="203.0.113.1", egress_interface="eth1"),
    ]
    findings = analyze_routes("fw-1", routes)
    assert any("conflicting" in f["message"].lower() for f in findings)


def test_flags_route_with_no_forwarding_target():
    routes = [
        RouteEntry(device_id="fw-1", destination_subnet="10.5.0.0/16", next_hop="", egress_interface=""),
        RouteEntry(device_id="fw-1", destination_subnet="0.0.0.0/0", next_hop="203.0.113.1", egress_interface="eth1"),
    ]
    findings = analyze_routes("fw-1", routes)
    assert any("can't forward" in f["message"] for f in findings)


def test_empty_routes_gives_info_not_warning():
    findings = analyze_routes("fw-1", [])
    assert len(findings) == 1
    assert findings[0]["severity"] == "info"


def test_nat_rule_missing_translated_address_flagged():
    rules = [NatRule(device_id="fw-1", name="broken-nat", source="any", destination="any", translated_address="")]
    findings = analyze_nat("fw-1", rules)
    assert len(findings) == 1
    assert findings[0]["category"] == "nat"


def test_analyze_combines_routing_and_nat_findings():
    routes = []
    rules = [NatRule(device_id="fw-1", name="broken-nat", source="any", destination="any", translated_address="")]
    findings = analyze("fw-1", routes, rules)
    categories = {f["category"] for f in findings}
    assert "routing" in categories
    assert "nat" in categories
