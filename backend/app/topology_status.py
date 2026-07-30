"""
Live status snapshot for the manual topology canvas (Network Diagram
page).

This is intentionally a *pure* read-side module: it doesn't poll
devices itself (that's link_stats.poll_interface_stats /
scheduler.poll_all_health, already running on their own 5s/60s
cadence) -- it just assembles what's already been polled and stored
into the shape the frontend needs to color links and badge nodes.
Kept separate from api/network_diagram.py so both the plain GET
(initial paint) and the websocket stream (live updates) build from the
exact same function and can never drift out of sync.

Interface color/status vocabulary (matches the 4 states + 4 link
colors from the spec):
  up          -> green   (oper up, admin enabled)
  down        -> red     (oper down, admin enabled -- a real fault)
  admin_down  -> grey    (admin disabled -- expected/intentional)
  error       -> orange  (up, but elevated errors/drops -- degraded)
  unknown     -> grey    (never polled / driver couldn't tell)
"""
from __future__ import annotations

import hashlib
import json

from app.models import Interface, SEVERITY_LABELS, SEVERITY_RANK
from app.store import store

# An interface is considered "erroring" (orange, not a hard down) once
# either counter crosses this within the current 5s sample. Deliberately
# simple/global like the health-alarm thresholds in alerting.py.
ERROR_RATE_WARNING_THRESHOLD = 50


def classify_interface(iface: Interface) -> str:
    if iface.admin_status == "disabled":
        return "admin_down"
    if iface.oper_status == "up":
        if (iface.errors or 0) >= ERROR_RATE_WARNING_THRESHOLD or (iface.drops or 0) >= ERROR_RATE_WARNING_THRESHOLD:
            return "error"
        return "up"
    if iface.oper_status == "down":
        return "down"
    return "unknown"


def _interface_payload(iface: Interface) -> dict:
    classification = classify_interface(iface)
    return {
        "if_name": iface.if_name,
        "classification": classification,          # up | down | admin_down | error | unknown
        "admin_status": iface.admin_status,
        "oper_status": iface.oper_status,
        "utilization_pct": iface.utilization_pct,
        "tx_mbps": iface.tx_mbps,
        "rx_mbps": iface.rx_mbps,
        "errors": iface.errors,
        "drops": iface.drops,
    }


def build_status_snapshot() -> dict:
    """Returns {devices: {device_id: {...}}, interfaces: {device_id: {if_name: {...}}}}"""
    devices_out: dict = {}
    interfaces_out: dict = {}

    active_alarms = store.list_alarms(active_only=True, limit=2000)
    alarms_by_device: dict[str, list] = {}
    for a in active_alarms:
        alarms_by_device.setdefault(a.device_id, []).append(a)

    for device in store.list_devices():
        ifaces = store.get_interface_stats(device.device_id)
        interfaces_out[device.device_id] = {i.if_name: _interface_payload(i) for i in ifaces}

        dev_alarms = alarms_by_device.get(device.device_id, [])
        worst_rank = max((SEVERITY_RANK.get(a.severity.value, 0) for a in dev_alarms), default=-1)
        if worst_rank < 0:
            device_status = "ok"
        elif worst_rank >= SEVERITY_RANK["critical"]:
            device_status = "critical"
        elif worst_rank >= SEVERITY_RANK["high"]:
            device_status = "major"
        elif worst_rank >= SEVERITY_RANK["medium"]:
            device_status = "minor"
        else:
            device_status = "warning"

        devices_out[device.device_id] = {
            "status": device_status,             # ok | warning | minor | major | critical
            "alarm_count": len(dev_alarms),
            "alarms": [
                {
                    "alarm_id": a.alarm_id,
                    "name": a.metric,
                    "severity": a.severity.value,
                    "severity_label": SEVERITY_LABELS.get(a.severity.value, a.severity.value.title()),
                    "description": a.description,
                    "triggered_at": a.triggered_at.isoformat(),
                    "interface": (a.detail or {}).get("interface"),
                }
                for a in sorted(dev_alarms, key=lambda a: SEVERITY_RANK.get(a.severity.value, 0), reverse=True)
            ],
        }

    return {"devices": devices_out, "interfaces": interfaces_out}


def snapshot_fingerprint(snapshot: dict) -> str:
    """Cheap change-detection hash so the websocket stream only pushes
    a frame when something actually changed, instead of re-sending an
    identical payload every poll tick."""
    return hashlib.sha1(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()
