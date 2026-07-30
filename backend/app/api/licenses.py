from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import store
from app.drivers.factory import get_driver
from app.drivers.base import DriverNotSupported

router = APIRouter(prefix="/licenses", tags=["licenses"])


class LicenseResponse(BaseModel):
    device_id: str
    feature: str
    expiry_date: str | None
    remaining_days: int | None
    status: str
    description: str


def _to_response(lic) -> LicenseResponse:
    remaining = None
    if lic.expiry_date:
        remaining = (lic.expiry_date - datetime.utcnow()).days
    return LicenseResponse(
        device_id=lic.device_id, feature=lic.feature,
        expiry_date=lic.expiry_date.isoformat() if lic.expiry_date else None,
        remaining_days=remaining, status=lic.status, description=lic.description,
    )


@router.get("", response_model=list[LicenseResponse])
def list_licenses(device_id: str | None = None):
    """Real license/entitlement data pulled from each device (PAN-OS's
    `request license info`, FortiOS's license status API) -- not
    sample data. Cisco IOS devices don't have a driver implementation
    for this yet and simply won't appear here."""
    return [_to_response(l) for l in store.get_licenses(device_id=device_id)]


@router.post("/{device_id}/poll-now", response_model=list[LicenseResponse])
def poll_now(device_id: str):
    """On-demand poll -- useful right after onboarding, or to check a
    license status change without waiting for the 6-hour scheduled poll."""
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    driver = get_driver(device)
    driver.connect()
    try:
        licenses = driver.get_licenses()
    except DriverNotSupported as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.set_licenses(device_id, licenses)
    return [_to_response(l) for l in licenses]
