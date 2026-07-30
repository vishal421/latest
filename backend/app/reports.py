"""
Reports: assembles a real summary from data already collected by every
other module (devices, alarms, licenses, traffic) rather than being
its own data source. No new polling, no synthetic numbers -- this is
what "reporting" means when the underlying data is already real:
structured aggregation, not generation.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.store import store
from app import traffic_analytics as ta


def generate_summary_report(since_minutes: int = 1440) -> dict:
    """Default window is 24h (1440 minutes) -- a report is meant to
    cover a meaningful period, not a live snapshot like the dashboard."""
    since = datetime.utcnow() - timedelta(minutes=since_minutes)

    devices = store.list_devices()
    device_by_vendor: dict[str, int] = {}
    for d in devices:
        device_by_vendor[d.vendor.value] = device_by_vendor.get(d.vendor.value, 0) + 1

    all_alarms = store.list_alarms(limit=5000)
    alarms_in_window = [a for a in all_alarms if a.triggered_at >= since]
    active_alarms = [a for a in all_alarms if a.resolved_at is None]

    all_licenses = store.get_licenses()
    expiring_soon = [
        l for l in all_licenses
        if l.expiry_date and 0 <= (l.expiry_date - datetime.utcnow()).days <= 30
    ]

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "window_minutes": since_minutes,
        "devices": {
            "total": len(devices),
            "by_vendor": device_by_vendor,
        },
        "alarms": {
            "triggered_in_window": len(alarms_in_window),
            "currently_active": len(active_alarms),
            "active_critical": sum(1 for a in active_alarms if a.severity.value == "critical"),
            "active_high": sum(1 for a in active_alarms if a.severity.value == "high"),
        },
        "licenses": {
            "total_tracked": len(all_licenses),
            "expiring_within_30_days": [
                {"device_id": l.device_id, "feature": l.feature, "expiry_date": l.expiry_date.isoformat()}
                for l in expiring_soon
            ],
        },
        "traffic": {
            "total_bytes": ta.total_traffic_bytes(since_minutes),
            "top_applications": ta.top_applications(since_minutes, limit=5),
            "denied_count": len(ta.denied_traffic(since_minutes, limit=1000)),
        },
    }
