from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.models import DiagramNode, DiagramEdge
from app.store import store
from app.topology_status import build_status_snapshot, snapshot_fingerprint

logger = logging.getLogger("infraos.network_diagram")

router = APIRouter(prefix="/network-diagram", tags=["network-diagram"])

# How often the websocket loop re-checks the store for changes. Cheap
# in-memory/DB reads (same data link_stats already polls onto every
# 5s), so this just decides push *latency*, not extra device load --
# no new vendor calls happen here.
STATUS_PUSH_INTERVAL_SECONDS = 2

# The palette: every icon type the diagram editor can place. Kept as
# one source of truth here so the frontend palette and backend
# validation never drift apart.
NODE_TYPES = [
    {"type": "access_point", "label": "Access Point"},
    {"type": "l2_switch", "label": "L2 Switch"},
    {"type": "l3_switch", "label": "L3 Switch"},
    {"type": "router", "label": "Router"},
    {"type": "firewall", "label": "Firewall"},
    {"type": "isp", "label": "ISP"},
    {"type": "server", "label": "Server"},
    {"type": "other", "label": "Other"},
]
_VALID_TYPES = {t["type"] for t in NODE_TYPES}


class NodeRequest(BaseModel):
    node_type: str
    label: str
    device_id: Optional[str] = None
    pos_x: float = 0.0
    pos_y: float = 0.0


class NodeUpdateRequest(BaseModel):
    node_type: Optional[str] = None
    label: Optional[str] = None
    device_id: Optional[str] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None


class EdgeRequest(BaseModel):
    node_a: str
    node_b: str
    interface_a: Optional[str] = None
    interface_b: Optional[str] = None


@router.get("/node-types")
def list_node_types():
    return NODE_TYPES


@router.get("")
def get_diagram():
    return {
        "nodes": [n.__dict__ for n in store.list_diagram_nodes()],
        "edges": [e.__dict__ for e in store.list_diagram_edges()],
        "status": build_status_snapshot(),
    }


@router.get("/status")
def get_status():
    """Same snapshot the websocket stream pushes -- useful as a plain
    polling fallback (or for a client that just reconnected and wants
    one fresh read without waiting for the next push tick)."""
    return build_status_snapshot()


@router.websocket("/ws/status")
async def status_stream(websocket: WebSocket):
    """Pushes {devices, interfaces} status snapshots so the topology
    canvas can recolor links and update alarm badges without the user
    refreshing the page. Only sends a frame when the snapshot actually
    changed since the last one sent, so an idle topology with no
    activity ends up nearly silent on the wire even though hundreds of
    devices are being checked every couple seconds."""
    await websocket.accept()
    last_fingerprint: Optional[str] = None
    try:
        while True:
            snapshot = await asyncio.get_event_loop().run_in_executor(None, build_status_snapshot)
            fingerprint = snapshot_fingerprint(snapshot)
            if fingerprint != last_fingerprint:
                await websocket.send_json(snapshot)
                last_fingerprint = fingerprint
            await asyncio.sleep(STATUS_PUSH_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001 -- never let a bad snapshot kill the app
        logger.warning("status stream error: %s", exc)


@router.post("/nodes")
def create_node(req: NodeRequest):
    if req.node_type not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown node_type. Valid: {sorted(_VALID_TYPES)}")
    if req.device_id and not store.get_device(req.device_id):
        raise HTTPException(status_code=404, detail="No such onboarded device")
    node = DiagramNode(node_id=str(uuid.uuid4()), node_type=req.node_type, label=req.label,
                        device_id=req.device_id, pos_x=req.pos_x, pos_y=req.pos_y)
    return store.save_diagram_node(node).__dict__


@router.patch("/nodes/{node_id}")
def update_node(node_id: str, req: NodeUpdateRequest):
    existing = next((n for n in store.list_diagram_nodes() if n.node_id == node_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="Node not found")
    if req.device_id is not None and req.device_id != "" and not store.get_device(req.device_id):
        raise HTTPException(status_code=404, detail="No such onboarded device")
    node = DiagramNode(
        node_id=node_id,
        node_type=req.node_type if req.node_type is not None else existing.node_type,
        label=req.label if req.label is not None else existing.label,
        device_id=req.device_id if req.device_id is not None else existing.device_id,
        pos_x=req.pos_x if req.pos_x is not None else existing.pos_x,
        pos_y=req.pos_y if req.pos_y is not None else existing.pos_y,
    )
    return store.save_diagram_node(node).__dict__


@router.delete("/nodes/{node_id}")
def delete_node(node_id: str):
    store.delete_diagram_node(node_id)
    return {"status": "deleted"}


@router.post("/edges")
def create_edge(req: EdgeRequest):
    node_ids = {n.node_id for n in store.list_diagram_nodes()}
    if req.node_a not in node_ids or req.node_b not in node_ids:
        raise HTTPException(status_code=404, detail="Both nodes must exist on the diagram")
    edge = DiagramEdge(edge_id=str(uuid.uuid4()), node_a=req.node_a, node_b=req.node_b,
                        interface_a=req.interface_a, interface_b=req.interface_b)
    return store.save_diagram_edge(edge).__dict__


@router.delete("/edges/{edge_id}")
def delete_edge(edge_id: str):
    store.delete_diagram_edge(edge_id)
    return {"status": "deleted"}
