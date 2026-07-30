from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models import ConfigBackup
from app.store import store
from app.drivers.factory import get_driver
from app.drivers.base import DriverNotSupported
from app.config_pipeline import parse_and_store

router = APIRouter(prefix="/config-backups", tags=["config-backups"])


class ConfigBackupResponse(BaseModel):
    backup_id: int
    device_id: str
    taken_at: str
    status: str
    size_bytes: int
    error: str


def _to_response(b: ConfigBackup) -> ConfigBackupResponse:
    return ConfigBackupResponse(
        backup_id=b.backup_id, device_id=b.device_id, taken_at=b.taken_at.isoformat(),
        status=b.status, size_bytes=b.size_bytes, error=b.error,
    )


@router.get("", response_model=list[ConfigBackupResponse])
def list_backups(device_id: str | None = None):
    """Real configuration snapshots pulled straight from each device
    (see driver.get_running_config()) -- not sample rows. Polled daily,
    plus available on demand via poll-now."""
    return [_to_response(b) for b in store.list_config_backups(device_id=device_id)]


@router.get("/{backup_id}/content")
def get_backup_content(backup_id: int):
    content = store.get_config_backup_content(backup_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"backup_id": backup_id, "content": content}


@router.get("/{device_id}/insights")
def get_config_insights(device_id: str):
    """Structured routes/NAT/findings already parsed out of this
    device's latest successful config pull (see config_pipeline.py) --
    computed at onboarding and on every re-pull, not on demand here."""
    parsed = store.get_parsed_config(device_id)
    if parsed is None:
        raise HTTPException(status_code=404, detail="No parsed configuration yet for this device -- pull one from Actions.")
    return parsed


@router.post("/{device_id}/poll-now", response_model=ConfigBackupResponse)
def poll_now(device_id: str):
    """On-demand backup -- useful right after onboarding, or before a
    planned change, without waiting for the daily scheduled backup."""
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    driver = get_driver(device)
    driver.connect()
    try:
        content = driver.get_running_config()
    except DriverNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        backup = store.add_config_backup(ConfigBackup(
            device_id=device_id, taken_at=datetime.utcnow(), status="failed", error=str(exc),
        ))
        return _to_response(backup)
    backup = store.add_config_backup(ConfigBackup(
        device_id=device_id, taken_at=datetime.utcnow(), status="success",
        size_bytes=len(content.encode()), content=content,
    ))
    parse_and_store(device, backup)
    return _to_response(backup)
