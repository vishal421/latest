from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models import Device, Vendor, DeviceType, ConfigBackup
from app.store import store
from app.vault import vault
from app.drivers.factory import get_driver
from app.drivers.base import DriverNotSupported
from app.config_pipeline import parse_and_store

router = APIRouter(prefix="/devices", tags=["devices"])


class AddDeviceRequest(BaseModel):
    hostname: str
    mgmt_ip: str
    vendor: Vendor
    device_type: DeviceType
    username: str
    password: str | None = None
    api_key: str | None = None


class DeviceResponse(BaseModel):
    device_id: str
    hostname: str
    mgmt_ip: str
    vendor: Vendor
    device_type: DeviceType
    model: str
    os_version: str
    serial_number: str


def _to_response(d: Device) -> DeviceResponse:
    return DeviceResponse(
        device_id=d.device_id, hostname=d.hostname, mgmt_ip=d.mgmt_ip,
        vendor=d.vendor, device_type=d.device_type, model=d.model,
        os_version=d.os_version, serial_number=d.serial_number,
    )


@router.post("", response_model=DeviceResponse)
def add_device(req: AddDeviceRequest):
    credential = {"username": req.username}
    if req.password:
        credential["password"] = req.password
    if req.api_key:
        credential["api_key"] = req.api_key
    credential_ref = vault.store(credential)

    device = Device(
        device_id=str(uuid.uuid4()),
        hostname=req.hostname,
        mgmt_ip=req.mgmt_ip,
        vendor=req.vendor,
        device_type=req.device_type,
        credential_ref=credential_ref,
        driver=f"{req.vendor.value}Driver",
    )
    store.add_device(device)

    # Populate facts immediately so the admin sees real model/serial/OS
    # right after onboarding, not just what they typed in.
    try:
        driver = get_driver(device)
        driver.connect()
        device = driver.get_facts()
        store.add_device(device)
    except Exception as exc:  # noqa: BLE001
        # Device is still onboarded even if it's unreachable right now --
        # surface the error but don't block onboarding on connectivity.
        raise HTTPException(
            status_code=207,
            detail=f"Device added but could not be reached yet: {exc}",
        ) from exc

    try:
        content = driver.get_running_config()
        backup = store.add_config_backup(ConfigBackup(
            device_id=device.device_id, taken_at=datetime.utcnow(),
            status="success", size_bytes=len(content.encode()), content=content,
        ))
        parse_and_store(device, backup)
    except DriverNotSupported:
        pass  # this device type doesn't have a config-backup concept
    except Exception as exc:  # noqa: BLE001
        # Config pull failing shouldn't block onboarding -- the daily
        # scheduled poll (and Actions -> Pull Running Configuration)
        # will pick it up once whatever's wrong is fixed.
        store.add_config_backup(ConfigBackup(
            device_id=device.device_id, taken_at=datetime.utcnow(),
            status="failed", error=str(exc),
        ))

    return _to_response(device)


@router.get("", response_model=list[DeviceResponse])
def list_devices():
    return [_to_response(d) for d in store.list_devices()]


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(device_id: str):
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return _to_response(device)


@router.delete("/{device_id}")
def delete_device(device_id: str):
    if not store.get_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    store.delete_device(device_id)
    return {"status": "deleted"}
