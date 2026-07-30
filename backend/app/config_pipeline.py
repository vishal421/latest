"""Called immediately after every successful config pull -- onboarding,
the daily scheduled poll, and manual poll-now all funnel through this
one function, so parsing genuinely happens "the moment a device is
onboarded" and again every time its config changes, not only when
someone happens to open Troubleshooting.
"""
from __future__ import annotations

from dataclasses import asdict

from app.models import Device, ConfigBackup
from app.config_analysis import parse_static_routes, parse_nat_rules
from app.config_insights import analyze
from app.store import store


def parse_and_store(device: Device, backup: ConfigBackup) -> None:
    if backup.status != "success" or not backup.content:
        return
    routes = parse_static_routes(device.vendor, device.device_id, backup.content)
    nat_rules = parse_nat_rules(device.vendor, device.device_id, backup.content)
    findings = analyze(device.device_id, routes, nat_rules)
    store.save_parsed_config(
        device_id=device.device_id, backup_id=backup.backup_id,
        routes=[asdict(r) for r in routes],
        nat_rules=[asdict(n) for n in nat_rules],
        findings=findings,
    )
