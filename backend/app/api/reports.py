from __future__ import annotations

from fastapi import APIRouter, Query

from app.reports import generate_summary_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary")
def get_summary_report(since_minutes: int = Query(default=1440, description="Report window in minutes, default 24h")):
    """A real report assembled from every other module's real data --
    devices, alarms, licenses, traffic. No separate data
    source of its own; this is structured aggregation, not generation."""
    return generate_summary_report(since_minutes)
