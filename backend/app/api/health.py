from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import store
from app.drivers.factory import get_driver

router = APIRouter(prefix="/health", tags=["health"])


class HealthPoint(BaseModel):
    timestamp: str
    cpu_pct: float | None
    memory_pct: float | None
    uptime_seconds: int | None
    active_sessions: int | None


@router.get("/{device_id}", response_model=list[HealthPoint])
def get_health_history(device_id: str, limit: int = 100):
    if not store.get_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    history = store.get_health_history(device_id, limit=limit)
    return [
        HealthPoint(
            timestamp=h.timestamp.isoformat(), cpu_pct=h.cpu_pct,
            memory_pct=h.memory_pct, uptime_seconds=h.uptime_seconds,
            active_sessions=h.active_sessions,
        )
        for h in history
    ]


@router.post("/{device_id}/poll-now", response_model=HealthPoint)
def poll_now(device_id: str):
    """On-demand poll, useful right after onboarding when you don't
    want to wait for the next scheduled interval."""
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    driver = get_driver(device)
    driver.connect()
    snapshot = driver.health_check()
    store.add_health_snapshot(snapshot)
    return HealthPoint(
        timestamp=snapshot.timestamp.isoformat(), cpu_pct=snapshot.cpu_pct,
        memory_pct=snapshot.memory_pct, uptime_seconds=snapshot.uptime_seconds,
        active_sessions=snapshot.active_sessions,
    )
