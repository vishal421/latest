from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app import traffic_analytics as ta

router = APIRouter(prefix="/traffic-analytics", tags=["traffic-analytics"])


class TopEntry(BaseModel):
    key: str
    bytes_total: int
    count: int


class DeniedEntry(BaseModel):
    dst_ip: str
    matched_rule: str
    hits: int


class TrafficAnalyticsResponse(BaseModel):
    top_source_ips: list[TopEntry]
    top_destination_ips: list[TopEntry]
    top_applications: list[TopEntry]
    denied: list[DeniedEntry]
    total_bytes: int
    since_minutes: int


@router.get("", response_model=TrafficAnalyticsResponse)
def get_traffic_analytics(
    since_minutes: int = Query(default=60, description="Aggregation window in minutes"),
    device_id: str | None = None,
    limit: int = 10,
):
    """Real aggregation off logged traffic (see app/traffic_analytics.py)
    -- top talkers/applications ranked by actual byte volume where the
    vendor log exposed one, denied traffic grouped by the real matched
    rule name. Not sample data; empty results just mean no traffic
    logs have been polled yet for this window."""
    return TrafficAnalyticsResponse(
        top_source_ips=[TopEntry(**e) for e in ta.top_source_ips(since_minutes, limit, device_id)],
        top_destination_ips=[TopEntry(**e) for e in ta.top_destination_ips(since_minutes, limit, device_id)],
        top_applications=[TopEntry(**e) for e in ta.top_applications(since_minutes, limit, device_id)],
        denied=[DeniedEntry(**e) for e in ta.denied_traffic(since_minutes, limit, device_id)],
        total_bytes=ta.total_traffic_bytes(since_minutes, device_id),
        since_minutes=since_minutes,
    )
