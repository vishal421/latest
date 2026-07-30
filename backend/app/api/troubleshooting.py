from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.troubleshooting import run_troubleshooting

router = APIRouter(prefix="/troubleshooting", tags=["troubleshooting"])


class TroubleshootingRequest(BaseModel):
    src_ip: str
    dst_ip: str
    protocol: Optional[str] = None
    device_id: Optional[str] = None


class TroubleshootingStepResponse(BaseModel):
    stage: str
    device_id: Optional[str]
    status: str
    summary: str
    source: str
    detail: dict


class TroubleshootingResponse(BaseModel):
    src_ip: str
    dst_ip: str
    protocol: Optional[str]
    device_id: Optional[str]
    verdict: str
    steps: list[TroubleshootingStepResponse]


@router.post("", response_model=TroubleshootingResponse)
def run(req: TroubleshootingRequest):
    """Source/destination are mandatory; protocol and device are
    optional (device narrows the trace to one onboarded device instead
    of every router/firewall). Built entirely on already-collected
    data -- stored traffic logs, live session tables, and downloaded
    config backups -- rather than opening a fresh live connection to
    every device on every run."""
    result = run_troubleshooting(req.src_ip, req.dst_ip, req.protocol, req.device_id)
    return TroubleshootingResponse(
        src_ip=result.src_ip, dst_ip=result.dst_ip, protocol=result.protocol,
        device_id=result.device_id, verdict=result.verdict,
        steps=[
            TroubleshootingStepResponse(
                stage=s.stage, device_id=s.device_id, status=s.status,
                summary=s.summary, source=s.source, detail=s.detail,
            )
            for s in result.steps
        ],
    )
