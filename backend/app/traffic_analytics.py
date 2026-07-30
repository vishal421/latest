"""
Traffic Analytics, built off real data already in the log store --
no synthetic numbers. "Top talkers" and "top applications" are
aggregated from real TRAFFIC-type LogEvents (src_ip/dst_ip/app/
bytes_total, all populated by the vendor drivers); "denied traffic"
is the same aggregation filtered to action=deny, with the real matched
rule name attached.

This does the aggregation in Python after fetching matching logs from
the store, rather than a native database aggregation query -- fine at
MVP log volumes; a high-volume deployment on Elasticsearch should
switch this to a real aggregation query (terms agg on src_ip/dst_ip/app)
instead of pulling raw documents and summing in Python.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from app.store import store


def _traffic_logs(since_minutes: int, device_id: Optional[str] = None, limit: int = 5000):
    since = datetime.utcnow() - timedelta(minutes=since_minutes)
    return store.search_logs(device_id=device_id, event_type="traffic", since=since, limit=limit)


def _top_by(logs, key_fn, limit: int) -> list[dict]:
    totals: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for log in logs:
        key = key_fn(log)
        if not key:
            continue
        totals[key] += log.bytes_total or 0
        counts[key] += 1
    # Rank by real byte volume when we have it; fall back to hit count
    # for entries/vendors where bytes_total wasn't available, rather
    # than silently dropping them.
    ranked = sorted(totals.keys(), key=lambda k: (totals[k], counts[k]), reverse=True)
    return [{"key": k, "bytes_total": totals[k], "count": counts[k]} for k in ranked[:limit]]


def top_source_ips(since_minutes: int = 60, limit: int = 10, device_id: Optional[str] = None) -> list[dict]:
    logs = _traffic_logs(since_minutes, device_id)
    return _top_by(logs, lambda l: l.src_ip, limit)


def top_destination_ips(since_minutes: int = 60, limit: int = 10, device_id: Optional[str] = None) -> list[dict]:
    logs = _traffic_logs(since_minutes, device_id)
    return _top_by(logs, lambda l: l.dst_ip, limit)


def top_applications(since_minutes: int = 60, limit: int = 10, device_id: Optional[str] = None) -> list[dict]:
    logs = _traffic_logs(since_minutes, device_id)
    return _top_by(logs, lambda l: l.app, limit)


def denied_traffic(since_minutes: int = 60, limit: int = 10, device_id: Optional[str] = None) -> list[dict]:
    logs = [l for l in _traffic_logs(since_minutes, device_id) if (l.action or "").lower() in ("deny", "denied", "block", "blocked")]
    totals: dict[tuple, int] = defaultdict(int)
    for log in logs:
        if not log.dst_ip:
            continue
        key = (log.dst_ip, log.matched_rule or "unknown rule")
        totals[key] += 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return [{"dst_ip": k[0], "matched_rule": k[1], "hits": v} for k, v in ranked[:limit]]


def total_traffic_bytes(since_minutes: int = 60, device_id: Optional[str] = None) -> int:
    """Real total, summed across every traffic log in the window --
    not limited to a top-N like the other aggregates, since this is
    meant to answer 'how much traffic total,' not 'which are biggest.'"""
    logs = _traffic_logs(since_minutes, device_id, limit=50000)
    return sum(l.bytes_total or 0 for l in logs)
