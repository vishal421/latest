"""
Real alerting, off data we already poll.

No new vendor calls needed: health snapshots (60s poll) and interface
stats (5s poll) already carry everything these thresholds need. This
module is called right after each poll stores its data, so an alarm is
generated the same cycle a threshold is crossed, and resolved the same
cycle it clears -- not a separate cron re-scanning stale data.

Thresholds are deliberately simple and explicit (not vendor-specific
"is this normal for this platform" tuning) -- a real deployment would
want per-device or per-vendor overrides eventually, but a single global
threshold is honest about being a first pass, not a mock.
"""
from __future__ import annotations

from datetime import datetime

from app.models import HealthSnapshot, Interface, AlarmSeverity, Alarm
from app.store import store

CPU_CRITICAL = 90
CPU_WARNING = 75
MEMORY_CRITICAL = 90
MEMORY_WARNING = 80


def _apply_threshold(device_id: str, metric: str, value: float, critical: float, warning: float, label: str) -> None:
    existing = store.get_open_alarm(device_id, metric)

    if value >= critical:
        severity = AlarmSeverity.CRITICAL
    elif value >= warning:
        severity = AlarmSeverity.MEDIUM
    else:
        severity = None

    if severity is None:
        if existing:
            store.resolve_alarm(existing.alarm_id, datetime.utcnow())
        return

    if existing and existing.severity == severity:
        return  # already alarming at this severity, don't spam duplicate rows
    if existing and existing.severity != severity:
        store.resolve_alarm(existing.alarm_id, datetime.utcnow())

    store.create_alarm(Alarm(
        device_id=device_id, severity=severity, metric=metric,
        description=f"{label} at {value}% (threshold: {critical if severity == AlarmSeverity.CRITICAL else warning}%)",
        triggered_at=datetime.utcnow(), detail={"value": value},
    ))


def check_health_alarms(device_id: str, snapshot: HealthSnapshot) -> None:
    if snapshot.cpu_pct is not None:
        _apply_threshold(device_id, "cpu", snapshot.cpu_pct, CPU_CRITICAL, CPU_WARNING, "CPU utilization")
    if snapshot.memory_pct is not None:
        _apply_threshold(device_id, "memory", snapshot.memory_pct, MEMORY_CRITICAL, MEMORY_WARNING, "Memory utilization")


def check_interface_alarms(device_id: str, interfaces: list[Interface]) -> None:
    for iface in interfaces:
        metric = f"interface_down:{iface.if_name}"
        existing = store.get_open_alarm(device_id, metric)
        is_down = iface.admin_status != "disabled" and iface.oper_status == "down"

        if is_down:
            if existing:
                continue  # already alarming on this interface
            store.create_alarm(Alarm(
                device_id=device_id, severity=AlarmSeverity.HIGH, metric=metric,
                description=f"Interface {iface.if_name} is down",
                triggered_at=datetime.utcnow(), detail={"interface": iface.if_name},
            ))
        else:
            if existing:
                store.resolve_alarm(existing.alarm_id, datetime.utcnow())
