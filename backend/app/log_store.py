"""
Log storage. Real deployments should point this at Elasticsearch
(set INFRAOS_ELASTICSEARCH_URL) -- log volume is exactly the kind of
write-heavy, search-heavy data Postgres isn't the right tool for. For
local development without a running Elasticsearch instance, this falls
back to an in-memory list transparently, so `pytest` and casual local
testing don't require standing up the whole stack.

Both backends implement the same three methods (add, search), so
nothing else in the codebase needs to know which one is active.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from app.models import LogEvent, LogEventType

INDEX_NAME = "infraos-logs"


class InMemoryLogStore:
    def __init__(self):
        self._logs: list[LogEvent] = []

    def add(self, events: list[LogEvent]) -> None:
        self._logs.extend(events)

    def search(
        self,
        device_id: Optional[str] = None,
        src_ip: Optional[str] = None,
        dst_ip: Optional[str] = None,
        action: Optional[str] = None,
        event_type: Optional[str] = None,
        app: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 200,
    ) -> list[LogEvent]:
        results = self._logs
        if device_id:
            results = [e for e in results if e.device_id == device_id]
        if src_ip:
            results = [e for e in results if e.src_ip == src_ip]
        if dst_ip:
            results = [e for e in results if e.dst_ip == dst_ip]
        if action:
            results = [e for e in results if e.action == action]
        if event_type:
            results = [e for e in results if e.event_type.value == event_type]
        if app:
            results = [e for e in results if e.app == app]
        if since:
            results = [e for e in results if e.timestamp >= since]
        return sorted(results, key=lambda e: e.timestamp, reverse=True)[:limit]


class ElasticsearchLogStore:
    def __init__(self, url: str):
        from elasticsearch import Elasticsearch
        self._es = Elasticsearch(url)
        if not self._es.indices.exists(index=INDEX_NAME):
            self._es.indices.create(index=INDEX_NAME)

    def add(self, events: list[LogEvent]) -> None:
        for e in events:
            self._es.index(index=INDEX_NAME, document={
                "device_id": e.device_id,
                "timestamp": e.timestamp.isoformat(),
                "severity": e.severity,
                "event_type": e.event_type.value,
                "src_ip": e.src_ip,
                "dst_ip": e.dst_ip,
                "action": e.action,
                "raw_original": e.raw_original,
                "threat_name": e.threat_name,
                "url": e.url,
                "category": e.category,
                "user": e.user,
                "app": e.app,
                "bytes_total": e.bytes_total,
                "matched_rule": e.matched_rule,
            })

    def search(
        self,
        device_id: Optional[str] = None,
        src_ip: Optional[str] = None,
        dst_ip: Optional[str] = None,
        action: Optional[str] = None,
        event_type: Optional[str] = None,
        app: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 200,
    ) -> list[LogEvent]:
        must = []
        if device_id:
            must.append({"term": {"device_id": device_id}})
        if src_ip:
            must.append({"term": {"src_ip": src_ip}})
        if dst_ip:
            must.append({"term": {"dst_ip": dst_ip}})
        if action:
            must.append({"term": {"action": action}})
        if event_type:
            must.append({"term": {"event_type": event_type}})
        if app:
            must.append({"term": {"app": app}})
        if since:
            must.append({"range": {"timestamp": {"gte": since.isoformat()}}})

        query = {"bool": {"must": must}} if must else {"match_all": {}}
        resp = self._es.search(
            index=INDEX_NAME, query=query, size=limit,
            sort=[{"timestamp": {"order": "desc"}}],
        )
        events = []
        for hit in resp["hits"]["hits"]:
            src = hit["_source"]
            events.append(LogEvent(
                device_id=src["device_id"],
                timestamp=datetime.fromisoformat(src["timestamp"]),
                severity=src["severity"],
                event_type=LogEventType(src["event_type"]),
                src_ip=src.get("src_ip"),
                dst_ip=src.get("dst_ip"),
                action=src.get("action"),
                raw_original=src.get("raw_original", ""),
                threat_name=src.get("threat_name"),
                url=src.get("url"),
                category=src.get("category"),
                user=src.get("user"),
                app=src.get("app"),
                bytes_total=src.get("bytes_total"),
                matched_rule=src.get("matched_rule"),
            ))
        return events


_log_store_instance = None


def get_log_store():
    global _log_store_instance
    if _log_store_instance is not None:
        return _log_store_instance

    url = os.environ.get("INFRAOS_ELASTICSEARCH_URL")
    if url:
        try:
            _log_store_instance = ElasticsearchLogStore(url)
            return _log_store_instance
        except Exception as exc:
            import logging
            logging.getLogger("infraos.log_store").warning(
                "Could not connect to Elasticsearch at %s (%s) -- falling back to in-memory log storage", url, exc,
            )
    _log_store_instance = InMemoryLogStore()
    return _log_store_instance


def reset_log_store_for_tests():
    """Test-only helper -- forces a fresh in-memory store so tests
    don't leak log data between each other."""
    global _log_store_instance
    _log_store_instance = InMemoryLogStore()
