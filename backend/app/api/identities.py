"""
Identity-aware correlation (see the "differentiating features" design
discussion). No AD/LDAP or DHCP-lease integration exists yet -- this is
a manual binding API for now, so the diagnostics engine can resolve
"10.1.1.5" to "vish" instead of correlating by IP alone, without
waiting on that integration to exist first. Swap this for a real
directory/DHCP feed later without changing the resolve_identity()
contract other code depends on.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.models import Identity
from app.store import store

router = APIRouter(prefix="/identities", tags=["identities"])


class IdentityRequest(BaseModel):
    username: str
    ip_address: str
    mac_address: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class IdentityResponse(BaseModel):
    username: str
    ip_address: str
    mac_address: str | None
    valid_from: str
    valid_to: str | None


@router.post("", response_model=IdentityResponse)
def add_identity(req: IdentityRequest):
    identity = Identity(
        username=req.username, ip_address=req.ip_address, mac_address=req.mac_address,
        valid_from=req.valid_from or datetime.utcnow(), valid_to=req.valid_to,
    )
    store.add_identity(identity)
    return IdentityResponse(
        username=identity.username, ip_address=identity.ip_address,
        mac_address=identity.mac_address, valid_from=identity.valid_from.isoformat(),
        valid_to=identity.valid_to.isoformat() if identity.valid_to else None,
    )


@router.get("/resolve", response_model=IdentityResponse | None)
def resolve_identity(ip_address: str):
    identity = store.resolve_identity(ip_address)
    if not identity:
        return None
    return IdentityResponse(
        username=identity.username, ip_address=identity.ip_address,
        mac_address=identity.mac_address, valid_from=identity.valid_from.isoformat(),
        valid_to=identity.valid_to.isoformat() if identity.valid_to else None,
    )
