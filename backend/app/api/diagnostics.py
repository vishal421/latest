from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.diagnostics import run_diagnostics

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class DiagnosticsRequest(BaseModel):
    src_ip: str
    dst_ip: str
    port: int = 443
    protocol: str = "tcp"


class HopResponse(BaseModel):
    device_id: str
    hop_type: str
    passed: bool
    reason: str
    detail: dict


class DiagnosticsResponse(BaseModel):
    src_ip: str
    dst_ip: str
    port: int
    protocol: str
    verdict: str
    path_source: str
    hops: list[HopResponse]


@router.post("", response_model=DiagnosticsResponse)
def run(req: DiagnosticsRequest):
    """The 'why can't this user reach Facebook' endpoint. Uses
    topology-based path selection when there's enough wired topology
    data (see app/path_selection.py), falling back to checking every
    onboarded switch/router/firewall otherwise."""
    result = run_diagnostics(req.src_ip, req.dst_ip, req.port, req.protocol)
    return DiagnosticsResponse(
        src_ip=result.src_ip, dst_ip=result.dst_ip, port=result.port,
        protocol=result.protocol, verdict=result.verdict,
        path_source=result.path_source,
        hops=[
            HopResponse(device_id=h.device_id, hop_type=h.hop_type,
                        passed=h.passed, reason=h.reason, detail=h.detail)
            for h in result.hops
        ],
    )
