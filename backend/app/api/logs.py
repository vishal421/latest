from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.store import store

router = APIRouter(prefix="/logs", tags=["logs"])


class LogEventResponse(BaseModel):
    device_id: str
    timestamp: str
    severity: str
    event_type: str
    src_ip: str | None
    dst_ip: str | None
    action: str | None
    threat_name: str | None = None
    url: str | None = None
    category: str | None = None
    user: str | None = None
    raw_original: str | None = None
    app: str | None = None
    bytes_total: int | None = None
    matched_rule: str | None = None


@router.get("", response_model=list[LogEventResponse])
def search_logs(
    device_id: str | None = None,
    src_ip: str | None = None,
    dst_ip: str | None = None,
    action: str | None = None,
    event_type: str | None = Query(default=None, description="traffic | threat | url | system"),
    app: str | None = Query(default=None, description="filter by application, where the vendor log exposes one"),
    since_minutes: int = Query(default=60, description="Only logs from the last N minutes"),
    limit: int = 200,
):
    """Real log search across whichever log types have been polled
    (traffic/threat/url/system -- see app/scheduler.py's LOG_TYPES_TO_POLL).
    Filter with event_type to get just one tab's worth, e.g. the
    frontend's Threat Logs / URL Logs / System Logs tabs."""
    since = datetime.utcnow() - timedelta(minutes=since_minutes)
    events = store.search_logs(
        device_id=device_id, src_ip=src_ip, dst_ip=dst_ip,
        action=action, event_type=event_type, app=app, since=since, limit=limit,
    )
    return [
        LogEventResponse(
            device_id=e.device_id, timestamp=e.timestamp.isoformat(),
            severity=e.severity, event_type=e.event_type.value,
            src_ip=e.src_ip, dst_ip=e.dst_ip, action=e.action,
            threat_name=e.threat_name, url=e.url, category=e.category, user=e.user,
            raw_original=e.raw_original, app=e.app,
            bytes_total=e.bytes_total, matched_rule=e.matched_rule,
        )
        for e in events
    ]
