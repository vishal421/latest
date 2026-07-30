"""
ORM tables backing the persistent store. These mirror the dataclasses
in models.py closely, with JSON columns used for the handful of fields
that don't map cleanly to simple columns (detail dicts, hop lists).
"""
from __future__ import annotations

from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, JSON
from app.db import Base


class DeviceRow(Base):
    __tablename__ = "devices"
    device_id = Column(String, primary_key=True)
    hostname = Column(String)
    mgmt_ip = Column(String)
    vendor = Column(String)
    device_type = Column(String)
    model = Column(String, default="")
    os_version = Column(String, default="")
    serial_number = Column(String, default="")
    credential_ref = Column(String, default="")
    driver = Column(String, default="")
    last_seen = Column(DateTime, nullable=True)


class HealthSnapshotRow(Base):
    __tablename__ = "health_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String, index=True)
    timestamp = Column(DateTime)
    cpu_pct = Column(Float, nullable=True)
    memory_pct = Column(Float, nullable=True)
    uptime_seconds = Column(Integer, nullable=True)
    active_sessions = Column(Integer, nullable=True)


class DiagnosticsResultRow(Base):
    __tablename__ = "diagnostics_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime)
    src_ip = Column(String)
    dst_ip = Column(String)
    port = Column(Integer, nullable=True)
    protocol = Column(String)
    verdict = Column(String)
    path_source = Column(String)
    hops = Column(JSON)  # list of hop dicts -- structured but not queried on individually yet


class TopologyLinkRow(Base):
    __tablename__ = "topology_links"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_a = Column(String)
    interface_a = Column(String)
    device_b = Column(String)
    interface_b = Column(String)
    source = Column(String)  # manual | discovered


class CliTranscriptRow(Base):
    __tablename__ = "cli_transcripts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String, index=True)
    admin_user = Column(String)
    command = Column(String)
    output = Column(String)
    is_config = Column(Boolean, default=False)
    timestamp = Column(DateTime)


class InterfaceStatRow(Base):
    """Latest interface snapshot per (device_id, if_name) -- overwritten
    on every 5s poll rather than accumulated, since only the live value
    is needed for the topology canvas."""
    __tablename__ = "interface_stats"
    device_id = Column(String, primary_key=True)
    if_name = Column(String, primary_key=True)
    status = Column(String, default="unknown")
    admin_status = Column(String, default="unknown")
    oper_status = Column(String, default="unknown")
    vlan_id = Column(Integer, nullable=True)
    ip_address = Column(String, nullable=True)
    mac_address = Column(String, nullable=True)
    errors = Column(Integer, default=0)
    drops = Column(Integer, default=0)
    utilization_pct = Column(Float, nullable=True)
    tx_bytes = Column(Integer, nullable=True)
    rx_bytes = Column(Integer, nullable=True)
    tx_mbps = Column(Float, nullable=True)
    rx_mbps = Column(Float, nullable=True)


class InterfaceStatHistoryRow(Base):
    """Append-only time series of interface Tx/Rx samples -- what
    InterfaceStatRow deliberately doesn't keep (it only holds the
    latest value). This is what a real bandwidth-over-time chart reads
    from. No retention/pruning policy yet at MVP scale -- a real
    deployment polling many interfaces every 5s should add one (e.g.
    downsample or drop samples older than N days) before this grows
    unbounded."""
    __tablename__ = "interface_stat_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String, index=True)
    if_name = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    tx_mbps = Column(Float, nullable=True)
    rx_mbps = Column(Float, nullable=True)
    oper_status = Column(String, default="unknown")


class IdentityRow(Base):
    """Username <-> IP/MAC binding over time, for identity-aware
    correlation. Populated manually via the API for now (no AD/LDAP
    or DHCP-lease integration yet -- see README)."""
    __tablename__ = "identities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, index=True)
    ip_address = Column(String, index=True)
    mac_address = Column(String, nullable=True)
    valid_from = Column(DateTime)
    valid_to = Column(DateTime, nullable=True)


class AlarmRow(Base):
    """A real alarm generated from real polled data -- see
    app/alerting.py. `resolved_at` is null while the alarm is active;
    only one open alarm per (device_id, metric) is kept at a time."""
    __tablename__ = "alarms"
    alarm_id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String, index=True)
    severity = Column(String)
    metric = Column(String, index=True)
    description = Column(String)
    triggered_at = Column(DateTime)
    resolved_at = Column(DateTime, nullable=True)
    detail = Column(JSON, default=dict)


class LicenseRow(Base):
    """Latest known license snapshot per (device_id, feature) -- like
    interface stats, overwritten on each poll rather than accumulated,
    since only the current state matters for the License Status page."""
    __tablename__ = "licenses"
    device_id = Column(String, primary_key=True)
    feature = Column(String, primary_key=True)
    expiry_date = Column(DateTime, nullable=True)
    status = Column(String, default="unknown")
    description = Column(String, default="")
    last_polled = Column(DateTime, nullable=True)


class ConfigBackupRow(Base):
    """A real configuration snapshot -- accumulated (not overwritten)
    so backup history is browsable, unlike license/interface state
    which only track 'current.'"""
    __tablename__ = "config_backups"
    backup_id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String, index=True)
    taken_at = Column(DateTime)
    status = Column(String)
    size_bytes = Column(Integer, default=0)
    content = Column(String, default="")
    error = Column(String, default="")


class ParsedConfigRow(Base):
    """Structured routes/NAT/findings parsed out of the latest
    successful ConfigBackup for a device -- computed once when the
    backup lands (onboarding pull, daily scheduled pull, or a manual
    poll-now), not re-parsed on every troubleshooting run. One row per
    device; each new successful backup overwrites it."""
    __tablename__ = "parsed_configs"
    device_id = Column(String, primary_key=True)
    backup_id = Column(Integer, nullable=True)
    updated_at = Column(DateTime)
    routes = Column(JSON, default=list)
    nat_rules = Column(JSON, default=list)
    findings = Column(JSON, default=list)


class SessionSnapshotRow(Base):
    """Periodic snapshots of each firewall's live session table,
    polled on a schedule (see poll_all_sessions in scheduler.py) so
    Troubleshooting has real session history to correlate against
    instead of only whatever's live at the exact moment a trace runs.
    Retention-cleaned the same way traffic logs are."""
    __tablename__ = "session_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    src_ip = Column(String)
    src_port = Column(Integer, nullable=True)
    dst_ip = Column(String)
    dst_port = Column(Integer, nullable=True)
    protocol = Column(String, default="")
    app = Column(String, default="")
    state = Column(String, default="")


class DiagramNodeRow(Base):
    """One icon on the user-drawn network diagram -- see
    models.DiagramNode. Separate from TopologyLinkRow's auto-discovered
    device-to-device graph: this is the person's own drawing, which
    can include unmanaged hops (WiFi AP, ISP) that were never onboarded
    and have no polled data of their own."""
    __tablename__ = "diagram_nodes"
    node_id = Column(String, primary_key=True)
    node_type = Column(String)
    label = Column(String)
    device_id = Column(String, nullable=True)
    pos_x = Column(Float, default=0.0)
    pos_y = Column(Float, default=0.0)


class DiagramEdgeRow(Base):
    __tablename__ = "diagram_edges"
    edge_id = Column(String, primary_key=True)
    node_a = Column(String, index=True)
    node_b = Column(String, index=True)
    interface_a = Column(String, nullable=True)
    interface_b = Column(String, nullable=True)


class OrganizationProfileRow(Base):
    """Single-row settings profile -- there's no multi-user auth system
    yet (see the RBAC placeholder warnings elsewhere), so this is one
    real, persisted admin/org profile rather than per-user accounts."""
    __tablename__ = "organization_profile"
    id = Column(Integer, primary_key=True)
    admin_name = Column(String, default="")
    admin_email = Column(String, default="")
    organization_name = Column(String, default="")
    updated_at = Column(DateTime, nullable=True)
