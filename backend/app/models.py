"""
Normalized, vendor-agnostic data model for InfraOS.

Nothing outside the driver layer should ever need to know which vendor
a device is. Every driver returns data shaped like these classes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DeviceType(str, Enum):
    ROUTER = "router"
    SWITCH = "switch"
    AP = "ap"
    FIREWALL = "firewall"


class Vendor(str, Enum):
    PALOALTO = "paloalto"
    FORTIGATE = "fortigate"
    CISCO_IOS = "cisco_ios"  # placeholder for Phase 2


@dataclass
class Device:
    device_id: str
    hostname: str
    mgmt_ip: str
    vendor: Vendor
    device_type: DeviceType
    model: str = ""
    os_version: str = ""
    serial_number: str = ""
    credential_ref: str = ""   # pointer into the vault, never the secret itself
    driver: str = ""           # e.g. "PaloAltoDriver"
    last_seen: Optional[datetime] = None


@dataclass
class Interface:
    device_id: str
    if_name: str
    status: str = "unknown"       # up | down | unknown  (kept for backward compat = oper_status)
    admin_status: str = "unknown" # enabled | disabled | unknown
    oper_status: str = "unknown"  # up | down | unknown
    vlan_id: Optional[int] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    errors: int = 0
    drops: int = 0
    utilization_pct: Optional[float] = None
    tx_bytes: Optional[int] = None       # raw counter, if the vendor exposes one
    rx_bytes: Optional[int] = None
    tx_mbps: Optional[float] = None      # computed from counter deltas between polls
    rx_mbps: Optional[float] = None
    connected_to_device: Optional[str] = None   # device_id of link partner
    connected_to_interface: Optional[str] = None


@dataclass
class RouteEntry:
    device_id: str
    destination_subnet: str
    next_hop: str
    egress_interface: str = ""
    protocol: str = "static"       # static | ospf | bgp | connected


@dataclass
class MacArpEntry:
    device_id: str
    mac_address: str
    ip_address: Optional[str]
    vlan_id: Optional[int]
    interface: str
    last_seen: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Session:
    device_id: str
    src_ip: str
    dst_ip: str
    src_port: Optional[int]
    dst_port: Optional[int]
    protocol: str
    app: Optional[str] = None
    nat_translation: Optional[str] = None
    state: str = "unknown"


@dataclass
class PolicyRule:
    device_id: str
    rule_id: str
    name: str
    action: str                    # allow | deny
    source_zone: str = ""
    dest_zone: str = ""
    source: str = "any"
    destination: str = "any"
    service: str = "any"
    hit_count: int = 0


class LogEventType(str, Enum):
    TRAFFIC = "traffic"
    SYSTEM = "system"
    THREAT = "threat"
    URL = "url"


@dataclass
class LogEvent:
    device_id: str
    timestamp: datetime
    severity: str
    event_type: LogEventType
    src_ip: Optional[str] = None
    dst_ip: Optional[str] = None
    action: Optional[str] = None    # allow | deny
    raw_original: str = ""
    # Populated only for the log types where they're meaningful --
    # threat_name for THREAT, url/category for URL, user for URL/SYSTEM
    # where the vendor log includes it. None elsewhere, not a mock value.
    threat_name: Optional[str] = None
    url: Optional[str] = None
    category: Optional[str] = None
    user: Optional[str] = None
    app: Optional[str] = None       # application/App-ID, where the vendor log exposes one
    bytes_total: Optional[int] = None    # traffic-log byte count, where the vendor log exposes one
    matched_rule: Optional[str] = None   # the policy/rule name that allowed or denied this flow


@dataclass
class DiscoveredNeighbor:
    """Raw CDP/LLDP neighbor info from a device, before it's resolved
    into a TopologyLink (resolution needs both sides' device_id, which
    the topology engine does by matching hostname/mgmt_ip against
    onboarded devices)."""
    device_id: str
    local_interface: str
    neighbor_hostname: str
    neighbor_interface: str
    neighbor_mgmt_ip: Optional[str] = None


@dataclass
class TopologyLink:
    device_a: str
    interface_a: str
    device_b: str
    interface_b: str
    source: str = "manual"          # manual | discovered


@dataclass
class Identity:
    username: str
    ip_address: str
    mac_address: Optional[str]
    valid_from: datetime
    valid_to: Optional[datetime] = None


@dataclass
class HealthSnapshot:
    device_id: str
    timestamp: datetime
    cpu_pct: Optional[float] = None
    memory_pct: Optional[float] = None
    uptime_seconds: Optional[int] = None
    active_sessions: Optional[int] = None


@dataclass
class HopResult:
    """One hop in the automated diagnostics trace (Section H of the design doc)."""
    device_id: str
    hop_type: str          # switch | router | firewall | logs
    passed: bool
    reason: str
    detail: dict = field(default_factory=dict)


@dataclass
class DiagnosticsResult:
    src_ip: str
    dst_ip: str
    port: Optional[int]
    protocol: str
    hops: list[HopResult]
    verdict: str            # plain-language root cause summary
    path_source: str = "fallback-all-devices"  # "topology" | "fallback-all-devices"


@dataclass
class TroubleshootingStep:
    """One stage of the traffic-log/session-log/config-file-backed
    troubleshooting trace. `source` names which of the three backbone
    data sources this stage's evidence actually came from, so the UI
    (and whoever's reading this) can see it's real collected data, not
    a live guess."""
    stage: str              # router_log | firewall_traffic | nat | routing | return_traffic
    device_id: Optional[str]
    status: str              # pass | fail | not_applicable
    summary: str
    source: str               # traffic_log | session_log | config_file | n/a
    detail: dict = field(default_factory=dict)


@dataclass
class TroubleshootingResult:
    src_ip: str
    dst_ip: str
    protocol: Optional[str]
    device_id: Optional[str]
    steps: list[TroubleshootingStep]
    verdict: str


@dataclass
class DiagramNode:
    """One icon on the user-drawn network diagram. node_type drives
    which icon renders (access_point | l2_switch | l3_switch | router
    | firewall | isp | other). device_id is set when the person maps
    this icon to a real onboarded device -- left None for unmanaged
    hops (a WiFi AP with no API, an ISP handoff) that still belong in
    the picture but can't be polled."""
    node_id: str
    node_type: str
    label: str
    device_id: Optional[str] = None
    pos_x: float = 0.0
    pos_y: float = 0.0


@dataclass
class DiagramEdge:
    """A drawn connection between two diagram nodes. interface_a/b are
    only meaningful when the corresponding node is device-mapped --
    picked from that device's real interface list, not free text."""
    edge_id: str
    node_a: str
    node_b: str
    interface_a: Optional[str] = None
    interface_b: Optional[str] = None


class AlarmSeverity(str, Enum):
    """Maps to the 5-tier severity vocabulary shown in the UI (topology
    alarm badges, alarm lists): critical->Critical, high->Major,
    medium->Minor, low->Warning, information->Information. INFORMATION
    is additive -- nothing existing produces it yet, but drivers/
    alerting.py can raise purely informational notices (e.g. "interface
    flapped and recovered") without them being conflated with an actual
    warning-level condition."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATION = "information"


SEVERITY_LABELS: dict[str, str] = {
    "critical": "Critical",
    "high": "Major",
    "medium": "Minor",
    "low": "Warning",
    "information": "Information",
}

# Ordered worst-to-best, used to roll a device's/link's many alarms up
# into a single "worst active severity" for badges and status dots.
SEVERITY_RANK: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "information": 0,
}


@dataclass
class Alarm:
    """A real alarm generated from real polled data (health snapshots,
    interface state) -- not a mock. See app/alerting.py for the
    threshold logic that creates and resolves these."""
    device_id: str
    severity: AlarmSeverity
    metric: str            # e.g. "cpu", "memory", "interface_down"
    description: str
    triggered_at: datetime
    alarm_id: Optional[int] = None
    resolved_at: Optional[datetime] = None
    detail: dict = field(default_factory=dict)


@dataclass
class License:
    """A real license entry pulled from the device itself (PAN-OS's
    `request license info` op-command, FortiOS's license status API)
    -- not a mock. `expiry_date` is None for perpetual/no-expiry
    licenses, which is a legitimate real state, not missing data."""
    device_id: str
    feature: str
    expiry_date: Optional[datetime] = None
    status: str = "unknown"      # active | expired | unknown
    description: str = ""


@dataclass
class ConfigBackup:
    """A real configuration snapshot pulled straight from a device
    (get_running_config()), not a mock backup entry. `content` is the
    raw config text; kept out of the list-view API response (too
    large) and fetched separately by ID."""
    device_id: str
    taken_at: datetime
    status: str          # success | failed
    size_bytes: int = 0
    content: str = ""
    error: str = ""
    backup_id: Optional[int] = None



