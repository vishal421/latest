from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import store
from app.drivers.factory import get_driver
from app.drivers.base import DriverNotSupported

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionResponse(BaseModel):
    device_id: str
    src_ip: str
    dst_ip: str
    src_port: int | None
    dst_port: int | None
    protocol: str
    app: str | None
    nat_translation: str | None
    state: str


@router.get("/{device_id}", response_model=list[SessionResponse])
def get_sessions(device_id: str, src_ip: str | None = None, dst_ip: str | None = None):
    """Real, live session/flow data queried directly from the device --
    firewall session tables (PAN-OS/FortiOS) or router NetFlow cache
    (Cisco IOS). Used by the diagnostics engine internally, and exposed
    here directly for manual correlation: e.g. confirm a flow actually
    transited a specific router, independent of running a full trace."""
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    driver = get_driver(device)
    driver.connect()
    try:
        sessions = driver.get_sessions(src_ip=src_ip, dst_ip=dst_ip)
    except DriverNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [
        SessionResponse(
            device_id=device_id, src_ip=s.src_ip, dst_ip=s.dst_ip,
            src_port=s.src_port, dst_port=s.dst_port, protocol=s.protocol,
            app=s.app, nat_translation=s.nat_translation, state=s.state,
        )
        for s in sessions
    ]
