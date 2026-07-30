from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models import TopologyLink
from app.topology import topology_store, run_discovery
from app.drift import compute_drift
from app.store import store

router = APIRouter(prefix="/topology", tags=["topology"])


class LinkRequest(BaseModel):
    device_a: str
    interface_a: str
    device_b: str
    interface_b: str


class LinkResponse(BaseModel):
    device_a: str
    interface_a: str
    device_b: str
    interface_b: str
    source: str


class InterfaceInfo(BaseModel):
    if_name: str
    ip_address: str | None
    mac_address: str | None
    admin_status: str
    oper_status: str
    tx_mbps: float | None
    rx_mbps: float | None


class NodeInfo(BaseModel):
    device_id: str
    hostname: str
    vendor: str
    device_type: str


class LinkEndpointStatus(BaseModel):
    admin_status: str
    oper_status: str
    ip_address: str | None
    mac_address: str | None
    tx_mbps: float | None
    rx_mbps: float | None


class GraphLink(BaseModel):
    device_a: str
    interface_a: str
    device_b: str
    interface_b: str
    source: str
    a_status: LinkEndpointStatus
    b_status: LinkEndpointStatus


class GraphResponse(BaseModel):
    nodes: list[NodeInfo]
    links: list[GraphLink]


def _to_response(l: TopologyLink) -> LinkResponse:
    return LinkResponse(
        device_a=l.device_a, interface_a=l.interface_a,
        device_b=l.device_b, interface_b=l.interface_b, source=l.source,
    )


def _endpoint_status(device_id: str, if_name: str) -> LinkEndpointStatus:
    interfaces = store.get_interface_stats(device_id)
    match = next((i for i in interfaces if i.if_name == if_name), None)
    if not match:
        return LinkEndpointStatus(
            admin_status="unknown", oper_status="unknown",
            ip_address=None, mac_address=None, tx_mbps=None, rx_mbps=None,
        )
    return LinkEndpointStatus(
        admin_status=match.admin_status, oper_status=match.oper_status,
        ip_address=match.ip_address, mac_address=match.mac_address,
        tx_mbps=match.tx_mbps, rx_mbps=match.rx_mbps,
    )


@router.post("/links", response_model=LinkResponse)
def add_manual_link(req: LinkRequest):
    link = TopologyLink(
        device_a=req.device_a, interface_a=req.interface_a,
        device_b=req.device_b, interface_b=req.interface_b,
    )
    topology_store.add_manual_link(link)
    return _to_response(link)


@router.get("/links", response_model=list[LinkResponse])
def list_links(source: str | None = None):
    return [_to_response(l) for l in topology_store.list_links(source=source)]


@router.post("/discover", response_model=list[LinkResponse])
def discover():
    links = run_discovery()
    return [_to_response(l) for l in links]


class InterfaceHistoryPoint(BaseModel):
    device_id: str
    if_name: str
    timestamp: str
    tx_mbps: float | None
    rx_mbps: float | None
    oper_status: str


@router.get("/interfaces/{device_id}", response_model=list[InterfaceInfo])
def get_device_interfaces(device_id: str):
    """Used by the 'define a link' UI: lists a device's interfaces with
    IP/MAC/status already fetched, so the admin only has to pick one --
    nothing is typed in by hand."""
    if not store.get_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    interfaces = store.get_interface_stats(device_id)
    return [
        InterfaceInfo(
            if_name=i.if_name, ip_address=i.ip_address, mac_address=i.mac_address,
            admin_status=i.admin_status, oper_status=i.oper_status,
            tx_mbps=i.tx_mbps, rx_mbps=i.rx_mbps,
        )
        for i in interfaces
    ]


class DriftEntryResponse(BaseModel):
    device_a: str
    device_b: str
    drift_type: str
    manual_interfaces: tuple | None
    discovered_interfaces: tuple | None


@router.get("/drift", response_model=list[DriftEntryResponse])
def get_drift():
    """Compares the manually-drawn topology against CDP/LLDP-discovered
    reality and flags mismatches -- links drawn but not seen live,
    links discovered but never drawn, or drawn on the wrong interface."""
    return [
        DriftEntryResponse(
            device_a=d.device_a, device_b=d.device_b, drift_type=d.drift_type,
            manual_interfaces=d.manual_interfaces, discovered_interfaces=d.discovered_interfaces,
        )
        for d in compute_drift()
    ]


@router.get("/graph", response_model=GraphResponse)
def get_graph():
    """Everything the visual topology canvas needs in one call: device
    nodes, links (manual + discovered), and each link endpoint's live
    status/traffic -- refreshed every 5 seconds by the interface-stats
    poller, polled by the frontend on the same cadence."""
    nodes = [
        NodeInfo(device_id=d.device_id, hostname=d.hostname,
                 vendor=d.vendor.value, device_type=d.device_type.value)
        for d in store.list_devices()
    ]
    links = []
    for l in topology_store.list_links():
        links.append(GraphLink(
            device_a=l.device_a, interface_a=l.interface_a,
            device_b=l.device_b, interface_b=l.interface_b, source=l.source,
            a_status=_endpoint_status(l.device_a, l.interface_a),
            b_status=_endpoint_status(l.device_b, l.interface_b),
        ))
    return GraphResponse(nodes=nodes, links=links)


@router.get("/interfaces/{device_id}/history", response_model=list[InterfaceHistoryPoint])
def get_interface_history(device_id: str, if_name: str | None = None, since_minutes: int = 60):
    """Real bandwidth-over-time data (see store.get_interface_stat_history) --
    sampled every ~60s, not every 5s (see app/link_stats.py for why),
    so this is coarser than the live topology view but real, not
    interpolated or faked."""
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(minutes=since_minutes)
    history = store.get_interface_stat_history(device_id=device_id, if_name=if_name, since=since)
    return [InterfaceHistoryPoint(**h) for h in history]
