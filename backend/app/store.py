"""
Persistent store, backed by Postgres (or SQLite locally/in tests) via
SQLAlchemy for structured data, and Elasticsearch (or an in-memory
fallback) for logs via log_store.py.

This used to be a plain in-memory object -- the public method
signatures are unchanged on purpose, so nothing in api/, diagnostics.py,
topology.py, scheduler.py, or link_stats.py had to change when this
swapped from in-memory to a real database. That was the whole point of
keeping this as its own module from Phase 1 onward.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.models import (
    Device, Vendor, DeviceType, HealthSnapshot, LogEvent,
    DiagnosticsResult, HopResult, Interface, Identity, Alarm, AlarmSeverity,
    License, ConfigBackup, Session, DiagramNode, DiagramEdge,
)
from app.db import get_session, init_db
from app.db_models import (
    DeviceRow, HealthSnapshotRow, DiagnosticsResultRow,
    CliTranscriptRow, InterfaceStatRow, InterfaceStatHistoryRow,
    IdentityRow, AlarmRow, LicenseRow, ConfigBackupRow,
    OrganizationProfileRow, ParsedConfigRow, SessionSnapshotRow,
    DiagramNodeRow, DiagramEdgeRow,
)
from app.log_store import get_log_store


def _device_to_row(d: Device) -> dict:
    return dict(
        device_id=d.device_id, hostname=d.hostname, mgmt_ip=d.mgmt_ip,
        vendor=d.vendor.value, device_type=d.device_type.value,
        model=d.model, os_version=d.os_version, serial_number=d.serial_number,
        credential_ref=d.credential_ref, driver=d.driver, last_seen=d.last_seen,
    )


def _row_to_device(row: DeviceRow) -> Device:
    return Device(
        device_id=row.device_id, hostname=row.hostname, mgmt_ip=row.mgmt_ip,
        vendor=Vendor(row.vendor), device_type=DeviceType(row.device_type),
        model=row.model or "", os_version=row.os_version or "",
        serial_number=row.serial_number or "", credential_ref=row.credential_ref or "",
        driver=row.driver or "", last_seen=row.last_seen,
    )


def _row_to_interface(row: InterfaceStatRow) -> Interface:
    return Interface(
        device_id=row.device_id, if_name=row.if_name, status=row.status,
        admin_status=row.admin_status, oper_status=row.oper_status,
        vlan_id=row.vlan_id, ip_address=row.ip_address, mac_address=row.mac_address,
        errors=row.errors or 0, drops=row.drops or 0, utilization_pct=row.utilization_pct,
        tx_bytes=row.tx_bytes, rx_bytes=row.rx_bytes, tx_mbps=row.tx_mbps, rx_mbps=row.rx_mbps,
    )


class Store:
    def __init__(self):
        init_db()

    # -- devices --
    def add_device(self, device: Device) -> None:
        with get_session() as session:
            session.merge(DeviceRow(**_device_to_row(device)))
            session.commit()

    def get_device(self, device_id: str) -> Optional[Device]:
        with get_session() as session:
            row = session.get(DeviceRow, device_id)
            return _row_to_device(row) if row else None

    def list_devices(self) -> list[Device]:
        with get_session() as session:
            return [_row_to_device(r) for r in session.query(DeviceRow).all()]

    def delete_device(self, device_id: str) -> None:
        with get_session() as session:
            row = session.get(DeviceRow, device_id)
            if row:
                session.delete(row)
            session.query(HealthSnapshotRow).filter(HealthSnapshotRow.device_id == device_id).delete()
            session.query(InterfaceStatRow).filter(InterfaceStatRow.device_id == device_id).delete()
            session.commit()

    # -- health --
    def add_health_snapshot(self, snapshot: HealthSnapshot) -> None:
        with get_session() as session:
            session.add(HealthSnapshotRow(
                device_id=snapshot.device_id, timestamp=snapshot.timestamp,
                cpu_pct=snapshot.cpu_pct, memory_pct=snapshot.memory_pct,
                uptime_seconds=snapshot.uptime_seconds, active_sessions=snapshot.active_sessions,
            ))
            session.commit()

    def get_health_history(self, device_id: str, limit: int = 100) -> list[HealthSnapshot]:
        with get_session() as session:
            rows = (
                session.query(HealthSnapshotRow)
                .filter(HealthSnapshotRow.device_id == device_id)
                .order_by(HealthSnapshotRow.timestamp.asc())
                .all()
            )
            rows = rows[-limit:]
            return [
                HealthSnapshot(
                    device_id=r.device_id, timestamp=r.timestamp, cpu_pct=r.cpu_pct,
                    memory_pct=r.memory_pct, uptime_seconds=r.uptime_seconds,
                    active_sessions=r.active_sessions,
                )
                for r in rows
            ]

    # -- logs (delegated to log_store: Elasticsearch or in-memory fallback) --
    def add_logs(self, events: list[LogEvent]) -> None:
        get_log_store().add(events)

    def search_logs(
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
        return get_log_store().search(
            device_id=device_id, src_ip=src_ip, dst_ip=dst_ip,
            action=action, event_type=event_type, app=app, since=since, limit=limit,
        )

    # -- diagnostics --
    def add_diagnostics_result(self, result: DiagnosticsResult) -> None:
        with get_session() as session:
            session.add(DiagnosticsResultRow(
                timestamp=datetime.utcnow(), src_ip=result.src_ip, dst_ip=result.dst_ip,
                port=result.port, protocol=result.protocol, verdict=result.verdict,
                path_source=result.path_source,
                hops=[
                    {"device_id": h.device_id, "hop_type": h.hop_type,
                     "passed": h.passed, "reason": h.reason, "detail": h.detail}
                    for h in result.hops
                ],
            ))
            session.commit()

    def get_diagnostics_history(self, limit: int = 50) -> list[DiagnosticsResult]:
        with get_session() as session:
            rows = (
                session.query(DiagnosticsResultRow)
                .order_by(DiagnosticsResultRow.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [
                DiagnosticsResult(
                    src_ip=r.src_ip, dst_ip=r.dst_ip, port=r.port, protocol=r.protocol,
                    verdict=r.verdict, path_source=r.path_source,
                    hops=[HopResult(**h) for h in (r.hops or [])],
                )
                for r in rows
            ]

    # -- CLI session audit --
    def record_cli_command(self, device_id: str, admin_user: str, command: str, output: str, is_config: bool = False) -> None:
        with get_session() as session:
            session.add(CliTranscriptRow(
                device_id=device_id, admin_user=admin_user, command=command,
                output=output, is_config=is_config, timestamp=datetime.utcnow(),
            ))
            session.commit()

    def get_cli_transcript(self, device_id: str) -> list[dict]:
        with get_session() as session:
            rows = (
                session.query(CliTranscriptRow)
                .filter(CliTranscriptRow.device_id == device_id)
                .order_by(CliTranscriptRow.timestamp.asc())
                .all()
            )
            return [
                {
                    "device_id": r.device_id, "admin_user": r.admin_user,
                    "command": r.command, "output": r.output,
                    "is_config": r.is_config, "timestamp": r.timestamp.isoformat(),
                }
                for r in rows
            ]

    def search_cli_transcripts(
        self, device_id: Optional[str] = None, admin_user: Optional[str] = None,
        config_only: bool = False, limit: int = 200,
    ) -> list[dict]:
        with get_session() as session:
            query = session.query(CliTranscriptRow)
            if device_id:
                query = query.filter(CliTranscriptRow.device_id == device_id)
            if admin_user:
                query = query.filter(CliTranscriptRow.admin_user == admin_user)
            if config_only:
                query = query.filter(CliTranscriptRow.is_config.is_(True))
            rows = query.order_by(CliTranscriptRow.timestamp.desc()).limit(limit).all()
            return [
                {
                    "device_id": r.device_id, "admin_user": r.admin_user,
                    "command": r.command, "output": r.output,
                    "is_config": r.is_config, "timestamp": r.timestamp.isoformat(),
                }
                for r in rows
            ]

    # -- live interface stats --
    def set_interface_stats(self, device_id: str, interfaces: list[Interface]) -> None:
        with get_session() as session:
            for iface in interfaces:
                row = session.get(InterfaceStatRow, (device_id, iface.if_name))
                data = dict(
                    device_id=device_id, if_name=iface.if_name, status=iface.status,
                    admin_status=iface.admin_status, oper_status=iface.oper_status,
                    vlan_id=iface.vlan_id, ip_address=iface.ip_address, mac_address=iface.mac_address,
                    errors=iface.errors, drops=iface.drops, utilization_pct=iface.utilization_pct,
                    tx_bytes=iface.tx_bytes, rx_bytes=iface.rx_bytes,
                    tx_mbps=iface.tx_mbps, rx_mbps=iface.rx_mbps,
                )
                if row:
                    for k, v in data.items():
                        setattr(row, k, v)
                else:
                    session.add(InterfaceStatRow(**data))
            session.commit()

    def get_interface_stats(self, device_id: str) -> list[Interface]:
        with get_session() as session:
            rows = session.query(InterfaceStatRow).filter(InterfaceStatRow.device_id == device_id).all()
            return [_row_to_interface(r) for r in rows]

    def add_interface_stat_samples(self, device_id: str, interfaces: list[Interface]) -> None:
        """Appends a history sample per interface -- separate from
        set_interface_stats(), which only overwrites the latest value.
        Only interfaces with an actual Mbps reading are recorded (no
        point charting a None)."""
        with get_session() as session:
            now = datetime.utcnow()
            for iface in interfaces:
                if iface.tx_mbps is None and iface.rx_mbps is None:
                    continue
                session.add(InterfaceStatHistoryRow(
                    device_id=device_id, if_name=iface.if_name, timestamp=now,
                    tx_mbps=iface.tx_mbps, rx_mbps=iface.rx_mbps, oper_status=iface.oper_status,
                ))
            session.commit()

    def get_interface_stat_history(
        self, device_id: Optional[str] = None, if_name: Optional[str] = None,
        since: Optional[datetime] = None, limit: int = 2000,
    ) -> list[dict]:
        with get_session() as session:
            query = session.query(InterfaceStatHistoryRow)
            if device_id:
                query = query.filter(InterfaceStatHistoryRow.device_id == device_id)
            if if_name:
                query = query.filter(InterfaceStatHistoryRow.if_name == if_name)
            if since:
                query = query.filter(InterfaceStatHistoryRow.timestamp >= since)
            rows = query.order_by(InterfaceStatHistoryRow.timestamp.asc()).limit(limit).all()
            return [
                {
                    "device_id": r.device_id, "if_name": r.if_name,
                    "timestamp": r.timestamp.isoformat(),
                    "tx_mbps": r.tx_mbps, "rx_mbps": r.rx_mbps, "oper_status": r.oper_status,
                }
                for r in rows
            ]

    # -- configuration backups (real, pulled from the device) --
    def add_config_backup(self, backup: ConfigBackup) -> ConfigBackup:
        with get_session() as session:
            row = ConfigBackupRow(
                device_id=backup.device_id, taken_at=backup.taken_at, status=backup.status,
                size_bytes=backup.size_bytes, content=backup.content, error=backup.error,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._row_to_backup(row, include_content=True)

    def list_config_backups(self, device_id: Optional[str] = None, limit: int = 100) -> list[ConfigBackup]:
        with get_session() as session:
            query = session.query(ConfigBackupRow)
            if device_id:
                query = query.filter(ConfigBackupRow.device_id == device_id)
            rows = query.order_by(ConfigBackupRow.taken_at.desc()).limit(limit).all()
            # Content omitted from the list view -- it can be large;
            # fetch it via get_config_backup_content(backup_id) instead.
            return [self._row_to_backup(r, include_content=False) for r in rows]

    def get_config_backup_content(self, backup_id: int) -> Optional[str]:
        with get_session() as session:
            row = session.get(ConfigBackupRow, backup_id)
            return row.content if row else None

    @staticmethod
    def _row_to_backup(row: ConfigBackupRow, include_content: bool) -> ConfigBackup:
        return ConfigBackup(
            backup_id=row.backup_id, device_id=row.device_id, taken_at=row.taken_at,
            status=row.status, size_bytes=row.size_bytes, error=row.error or "",
            content=row.content if include_content else "",
        )

    # -- parsed config (routes/NAT/findings derived from the latest
    # successful ConfigBackup -- see config_pipeline.py) --
    def save_parsed_config(self, device_id: str, backup_id: Optional[int],
                            routes: list[dict], nat_rules: list[dict], findings: list[dict]) -> None:
        with get_session() as session:
            row = session.get(ParsedConfigRow, device_id)
            if row is None:
                row = ParsedConfigRow(device_id=device_id)
                session.add(row)
            row.backup_id = backup_id
            row.updated_at = datetime.utcnow()
            row.routes = routes
            row.nat_rules = nat_rules
            row.findings = findings
            session.commit()

    def get_parsed_config(self, device_id: str) -> Optional[dict]:
        with get_session() as session:
            row = session.get(ParsedConfigRow, device_id)
            if row is None:
                return None
            return {
                "device_id": row.device_id, "backup_id": row.backup_id,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "routes": row.routes or [], "nat_rules": row.nat_rules or [], "findings": row.findings or [],
            }

    # -- session snapshots (periodic poll of each firewall's live
    # session table -- see poll_all_sessions in scheduler.py) --
    def add_sessions(self, device_id: str, sessions: list) -> None:
        if not sessions:
            return
        now = datetime.utcnow()
        with get_session() as session:
            for s in sessions:
                session.add(SessionSnapshotRow(
                    device_id=device_id, timestamp=now,
                    src_ip=s.src_ip, src_port=s.src_port, dst_ip=s.dst_ip, dst_port=s.dst_port,
                    protocol=s.protocol, app=getattr(s, "app", "") or "", state=getattr(s, "state", "") or "",
                ))
            session.commit()

    def search_sessions(self, device_id: Optional[str] = None, src_ip: Optional[str] = None,
                         dst_ip: Optional[str] = None, since: Optional[datetime] = None, limit: int = 200) -> list:
        with get_session() as session:
            query = session.query(SessionSnapshotRow)
            if device_id:
                query = query.filter(SessionSnapshotRow.device_id == device_id)
            if src_ip:
                query = query.filter(SessionSnapshotRow.src_ip == src_ip)
            if dst_ip:
                query = query.filter(SessionSnapshotRow.dst_ip == dst_ip)
            if since:
                query = query.filter(SessionSnapshotRow.timestamp >= since)
            rows = query.order_by(SessionSnapshotRow.timestamp.desc()).limit(limit).all()
            return [
                Session(device_id=r.device_id, src_ip=r.src_ip, src_port=r.src_port,
                        dst_ip=r.dst_ip, dst_port=r.dst_port, protocol=r.protocol,
                        app=r.app, state=r.state)
                for r in rows
            ]

    def cleanup_old_sessions(self, older_than: datetime) -> None:
        with get_session() as session:
            session.query(SessionSnapshotRow).filter(SessionSnapshotRow.timestamp < older_than).delete()
            session.commit()

    # -- network diagram (user-drawn, icon-based -- see DiagramNode/DiagramEdge) --
    def list_diagram_nodes(self) -> list[DiagramNode]:
        with get_session() as session:
            rows = session.query(DiagramNodeRow).all()
            return [DiagramNode(node_id=r.node_id, node_type=r.node_type, label=r.label,
                                 device_id=r.device_id, pos_x=r.pos_x, pos_y=r.pos_y) for r in rows]

    def save_diagram_node(self, node: DiagramNode) -> DiagramNode:
        with get_session() as session:
            row = session.get(DiagramNodeRow, node.node_id)
            if row is None:
                row = DiagramNodeRow(node_id=node.node_id)
                session.add(row)
            row.node_type = node.node_type
            row.label = node.label
            row.device_id = node.device_id
            row.pos_x = node.pos_x
            row.pos_y = node.pos_y
            session.commit()
            return node

    def delete_diagram_node(self, node_id: str) -> None:
        with get_session() as session:
            session.query(DiagramNodeRow).filter(DiagramNodeRow.node_id == node_id).delete()
            # A node's edges no longer make sense once it's gone.
            session.query(DiagramEdgeRow).filter(
                (DiagramEdgeRow.node_a == node_id) | (DiagramEdgeRow.node_b == node_id)
            ).delete()
            session.commit()

    def list_diagram_edges(self) -> list[DiagramEdge]:
        with get_session() as session:
            rows = session.query(DiagramEdgeRow).all()
            return [DiagramEdge(edge_id=r.edge_id, node_a=r.node_a, node_b=r.node_b,
                                 interface_a=r.interface_a, interface_b=r.interface_b) for r in rows]

    def save_diagram_edge(self, edge: DiagramEdge) -> DiagramEdge:
        with get_session() as session:
            row = session.get(DiagramEdgeRow, edge.edge_id)
            if row is None:
                row = DiagramEdgeRow(edge_id=edge.edge_id)
                session.add(row)
            row.node_a = edge.node_a
            row.node_b = edge.node_b
            row.interface_a = edge.interface_a
            row.interface_b = edge.interface_b
            session.commit()
            return edge

    def delete_diagram_edge(self, edge_id: str) -> None:
        with get_session() as session:
            session.query(DiagramEdgeRow).filter(DiagramEdgeRow.edge_id == edge_id).delete()
            session.commit()

    # -- organization/admin profile (single-row settings) --
    def get_organization_profile(self) -> dict:
        with get_session() as session:
            row = session.get(OrganizationProfileRow, 1)
            if not row:
                return {"admin_name": "", "admin_email": "", "organization_name": "", "updated_at": None}
            return {
                "admin_name": row.admin_name, "admin_email": row.admin_email,
                "organization_name": row.organization_name,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }

    def set_organization_profile(self, admin_name: str, admin_email: str, organization_name: str) -> dict:
        with get_session() as session:
            row = session.get(OrganizationProfileRow, 1)
            now = datetime.utcnow()
            if row:
                row.admin_name, row.admin_email, row.organization_name, row.updated_at = admin_name, admin_email, organization_name, now
            else:
                row = OrganizationProfileRow(
                    id=1, admin_name=admin_name, admin_email=admin_email,
                    organization_name=organization_name, updated_at=now,
                )
                session.add(row)
            session.commit()
            return {
                "admin_name": admin_name, "admin_email": admin_email,
                "organization_name": organization_name, "updated_at": now.isoformat(),
            }

    # -- identity (username <-> IP/MAC over time) --
    def add_identity(self, identity: Identity) -> None:
        with get_session() as session:
            session.add(IdentityRow(
                username=identity.username, ip_address=identity.ip_address,
                mac_address=identity.mac_address, valid_from=identity.valid_from,
                valid_to=identity.valid_to,
            ))
            session.commit()

    def resolve_identity(self, ip_address: str, at_time: Optional[datetime] = None) -> Optional[Identity]:
        """Returns the identity bound to this IP at the given time (or
        now, if not specified) -- the most recent binding that was
        valid at that moment, if any."""
        at_time = at_time or datetime.utcnow()
        with get_session() as session:
            rows = (
                session.query(IdentityRow)
                .filter(IdentityRow.ip_address == ip_address)
                .filter(IdentityRow.valid_from <= at_time)
                .order_by(IdentityRow.valid_from.desc())
                .all()
            )
            for r in rows:
                if r.valid_to is None or r.valid_to >= at_time:
                    return Identity(
                        username=r.username, ip_address=r.ip_address,
                        mac_address=r.mac_address, valid_from=r.valid_from, valid_to=r.valid_to,
                    )
            return None

    def clear_all_for_tests(self) -> None:
        """Test-only: wipes every table so each test starts from a
        clean slate. Never call this outside the test suite."""
        with get_session() as session:
            for row_cls in (DeviceRow, HealthSnapshotRow, DiagnosticsResultRow,
                            CliTranscriptRow, InterfaceStatRow, InterfaceStatHistoryRow,
                            IdentityRow, AlarmRow, LicenseRow, ConfigBackupRow,
                            OrganizationProfileRow, ParsedConfigRow, SessionSnapshotRow,
                            DiagramNodeRow, DiagramEdgeRow):
                session.query(row_cls).delete()
            session.commit()

    # -- licenses (real, pulled from the device -- see driver.get_licenses()) --
    def set_licenses(self, device_id: str, licenses: list[License]) -> None:
        with get_session() as session:
            session.query(LicenseRow).filter(LicenseRow.device_id == device_id).delete()
            now = datetime.utcnow()
            for lic in licenses:
                session.add(LicenseRow(
                    device_id=device_id, feature=lic.feature, expiry_date=lic.expiry_date,
                    status=lic.status, description=lic.description, last_polled=now,
                ))
            session.commit()

    def get_licenses(self, device_id: Optional[str] = None) -> list[License]:
        with get_session() as session:
            query = session.query(LicenseRow)
            if device_id:
                query = query.filter(LicenseRow.device_id == device_id)
            rows = query.all()
            return [
                License(
                    device_id=r.device_id, feature=r.feature, expiry_date=r.expiry_date,
                    status=r.status, description=r.description or "",
                )
                for r in rows
            ]

    # -- alarms (real, generated from real polled data -- see app/alerting.py) --
    def get_open_alarm(self, device_id: str, metric: str) -> Optional[Alarm]:
        with get_session() as session:
            row = (
                session.query(AlarmRow)
                .filter(AlarmRow.device_id == device_id, AlarmRow.metric == metric, AlarmRow.resolved_at.is_(None))
                .order_by(AlarmRow.triggered_at.desc())
                .first()
            )
            return self._row_to_alarm(row) if row else None

    def create_alarm(self, alarm: Alarm) -> Alarm:
        with get_session() as session:
            row = AlarmRow(
                device_id=alarm.device_id, severity=alarm.severity.value, metric=alarm.metric,
                description=alarm.description, triggered_at=alarm.triggered_at, detail=alarm.detail,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._row_to_alarm(row)

    def resolve_alarm(self, alarm_id: int, resolved_at: datetime) -> None:
        with get_session() as session:
            row = session.get(AlarmRow, alarm_id)
            if row:
                row.resolved_at = resolved_at
                session.commit()

    def list_alarms(
        self, device_id: Optional[str] = None, severity: Optional[str] = None,
        active_only: bool = False, limit: int = 200,
    ) -> list[Alarm]:
        with get_session() as session:
            query = session.query(AlarmRow)
            if device_id:
                query = query.filter(AlarmRow.device_id == device_id)
            if severity:
                query = query.filter(AlarmRow.severity == severity)
            if active_only:
                query = query.filter(AlarmRow.resolved_at.is_(None))
            rows = query.order_by(AlarmRow.triggered_at.desc()).limit(limit).all()
            return [self._row_to_alarm(r) for r in rows]

    @staticmethod
    def _row_to_alarm(row: AlarmRow) -> Alarm:
        return Alarm(
            alarm_id=row.alarm_id, device_id=row.device_id, severity=AlarmSeverity(row.severity),
            metric=row.metric, description=row.description, triggered_at=row.triggered_at,
            resolved_at=row.resolved_at, detail=row.detail or {},
        )


store = Store()
