from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.store import store

router = APIRouter(prefix="/alarms", tags=["alarms"])


class AlarmResponse(BaseModel):
    alarm_id: int
    device_id: str
    severity: str
    metric: str
    description: str
    triggered_at: str
    resolved_at: str | None
    status: str


def _to_response(a) -> AlarmResponse:
    return AlarmResponse(
        alarm_id=a.alarm_id, device_id=a.device_id, severity=a.severity.value,
        metric=a.metric, description=a.description,
        triggered_at=a.triggered_at.isoformat(),
        resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
        status="Resolved" if a.resolved_at else "Active",
    )


@router.get("", response_model=list[AlarmResponse])
def list_alarms(device_id: str | None = None, severity: str | None = None, active_only: bool = False, limit: int = 200):
    """Real alarms generated from real polled health/interface data
    (see app/alerting.py) -- not sample data."""
    return [_to_response(a) for a in store.list_alarms(device_id=device_id, severity=severity, active_only=active_only, limit=limit)]


@router.get("/summary")
def alarms_summary():
    """Counts for the dashboard summary cards."""
    active = store.list_alarms(active_only=True, limit=1000)
    return {
        "active_total": len(active),
        "critical": sum(1 for a in active if a.severity.value == "critical"),
        "high": sum(1 for a in active if a.severity.value == "high"),
        "medium": sum(1 for a in active if a.severity.value == "medium"),
        "low": sum(1 for a in active if a.severity.value == "low"),
    }
