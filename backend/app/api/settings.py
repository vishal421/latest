from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.store import store

router = APIRouter(prefix="/settings", tags=["settings"])


class ProfileRequest(BaseModel):
    admin_name: str
    admin_email: str
    organization_name: str


class ProfileResponse(BaseModel):
    admin_name: str
    admin_email: str
    organization_name: str
    updated_at: str | None


@router.get("/profile", response_model=ProfileResponse)
def get_profile():
    """A real, persisted admin/org profile -- there's no multi-user
    login system yet (see the RBAC placeholder warnings elsewhere in
    the codebase), so this is one real settings record rather than
    per-user accounts."""
    return ProfileResponse(**store.get_organization_profile())


@router.put("/profile", response_model=ProfileResponse)
def update_profile(req: ProfileRequest):
    return ProfileResponse(**store.set_organization_profile(req.admin_name, req.admin_email, req.organization_name))


@router.get("/license-summary")
def get_license_summary():
    """Consolidated real license counts for the Settings page -- same
    underlying data as the License Status page, summarized."""
    from datetime import datetime
    licenses = store.get_licenses()
    expiring = [l for l in licenses if l.expiry_date and 0 <= (l.expiry_date - datetime.utcnow()).days <= 30]
    expired = [l for l in licenses if l.status == "expired"]
    return {
        "total": len(licenses),
        "expiring_within_30_days": len(expiring),
        "expired": len(expired),
    }
