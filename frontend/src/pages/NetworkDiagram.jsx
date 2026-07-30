import { useEffect, useRef, useState } from "react";
import { Wifi, Network, Router, Share2, ShieldCheck, Globe, Server, Box, Trash2, Link2 } from "lucide-react";
import Card from "../components/Card";
import Modal from "../components/Modal";
import { api } from "../api";

const ICONS = {
  access_point: Wifi,
  l2_switch: Network,
  l3_switch: Share2,
  router: Router,
  firewall: ShieldCheck,
  isp: Globe,
  server: Server,
  other: Box,
};

const NODE_W = 96, NODE_H = 64;

// --- Real-time status → color helpers -------------------------------
// Link colors (spec): Green = Up, Red = Down, Orange = Warning, Grey = Unknown.
// "Administratively Down" gets its own grey-dashed treatment so it reads
// as an intentional state, not a fault.
const LINK_COLOR = {
  up: "var(--good)",
  down: "var(--bad)",
  error: "var(--warn)",
  admin_down: "var(--text-faint)",
  unknown: "var(--text-faint)",
};
const LINK_DASH = { admin_down: "4 3", unknown: "2 3" };

// Device/badge severity colors, worst-active-alarm rollup.
const DEVICE_STATUS_COLOR = {
  ok: "var(--good)",
  warning: "var(--warn)",
  minor: "var(--warn)",
  major: "var(--bad)",
  critical: "var(--critical)",
};
const SEVERITY_COLOR = {
  critical: "var(--critical)",
  high: "var(--bad)",
  medium: "var(--warn)",
  low: "var(--warn)",
  information: "var(--info)",
};
const SEVERITY_LABEL = {
  critical: "Critical", high: "Major", medium: "Minor", low: "Warning", information: "Information",
};

function ifaceClassification(status, deviceId, ifName) {
  if (!deviceId || !ifName) return null;
  return status?.interfaces?.[deviceId]?.[ifName]?.classification || null;
}

// An edge's color is the worse of its two mapped-interface classifications
// (a link is only as healthy as its most broken end). Edges with no
// interface mapped on either side stay neutral, same as before this
// feature existed.
const CLASS_SEVERITY = { down: 3, error: 2, unknown: 1, admin_down: 1, up: 0 };
function edgeClassification(status, a, b, edge) {
  const ca = ifaceClassification(status, a?.device_id, edge.interface_a);
  const cb = ifaceClassification(status, b?.device_id, edge.interface_b);
  if (!ca && !cb) return null;
  const pick = [ca, cb].filter(Boolean).sort((x, y) => (CLASS_SEVERITY[y] ?? 0) - (CLASS_SEVERITY[x] ?? 0))[0];
  return pick;
}

export default function NetworkDiagram() {
  const [nodeTypes, setNodeTypes] = useState([]);
  const [devices, setDevices] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [connectFrom, setConnectFrom] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [interfacesByDevice, setInterfacesByDevice] = useState({});
  const [status, setStatus] = useState({ devices: {}, interfaces: {} }); // live push from /network-diagram/ws/status
  const [connected, setConnected] = useState(false);
  const [hoverAlarms, setHoverAlarms] = useState(null); // { nodeId, x, y }
  const [alarmModalNode, setAlarmModalNode] = useState(null); // node whose full alarm list is open
  const dragRef = useRef(null); // { nodeId, offsetX, offsetY }
  const svgRef = useRef(null);
  const wsRef = useRef(null);

  const load = () => {
    api.getNetworkDiagram().then((g) => {
      setNodes(g.nodes); setEdges(g.edges);
      if (g.status) setStatus(g.status);
    });
  };

  useEffect(() => {
    api.getDiagramNodeTypes().then(setNodeTypes);
    api.listDevices().then(setDevices);
    load();
  }, []);

  // Real-time monitoring: one websocket for the whole canvas, pushing
  // {devices, interfaces} snapshots. Reconnects with backoff if the
  // connection drops so long-lived dashboard tabs keep updating.
  useEffect(() => {
    let cancelled = false;
    let retryDelay = 2000;
    let retryTimer;

    const connect = () => {
      const ws = api.openTopologyStatusStream(
        (snapshot) => { if (!cancelled) { setStatus(snapshot); setConnected(true); } },
        () => { if (!cancelled) setConnected(false); }
      );
      ws.onopen = () => { if (!cancelled) { setConnected(true); retryDelay = 2000; } };
      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.5, 15000);
      };
      wsRef.current = ws;
    };
    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, []);

  const addNode = async (nodeType) => {
    const created = await api.createDiagramNode({ node_type: nodeType, label: nodeType.replace("_", " "), pos_x: 60, pos_y: 60 });
    setNodes((prev) => [...prev, created]);
  };

  const svgPoint = (evt) => {
    const rect = svgRef.current.getBoundingClientRect();
    return { x: evt.clientX - rect.left, y: evt.clientY - rect.top };
  };

  const onNodeMouseDown = (node, evt) => {
    evt.stopPropagation();
    const p = svgPoint(evt);
    dragRef.current = { nodeId: node.node_id, offsetX: p.x - node.pos_x, offsetY: p.y - node.pos_y, moved: false };
  };

  const onMouseMove = (evt) => {
    if (!dragRef.current) return;
    const p = svgPoint(evt);
    const { nodeId, offsetX, offsetY } = dragRef.current;
    dragRef.current.moved = true;
    setNodes((prev) => prev.map((n) => n.node_id === nodeId ? { ...n, pos_x: p.x - offsetX, pos_y: p.y - offsetY } : n));
  };

  const onMouseUp = () => {
    if (!dragRef.current) return;
    const { nodeId, moved } = dragRef.current;
    dragRef.current = null;
    if (!moved) return;
    const node = nodes.find((n) => n.node_id === nodeId);
    if (node) api.updateDiagramNode(nodeId, { pos_x: node.pos_x, pos_y: node.pos_y });
  };

  const onNodeClick = (node) => {
    if (dragRef.current?.moved) return; // was a drag, not a click
    if (connecting) {
      if (!connectFrom) {
        setConnectFrom(node.node_id);
      } else if (connectFrom !== node.node_id) {
        api.createDiagramEdge({ node_a: connectFrom, node_b: node.node_id }).then((e) => setEdges((prev) => [...prev, e]));
        setConnectFrom(null);
      }
      return;
    }
    setSelectedNode(node);
    if (node.device_id && !interfacesByDevice[node.device_id]) {
      api.getDeviceInterfaces(node.device_id).then((ifs) =>
        setInterfacesByDevice((prev) => ({ ...prev, [node.device_id]: ifs }))
      ).catch(() => {});
    }
  };

  const saveNodeEdit = async (patch) => {
    const updated = await api.updateDiagramNode(selectedNode.node_id, patch);
    setNodes((prev) => prev.map((n) => n.node_id === updated.node_id ? updated : n));
    setSelectedNode(updated);
    if (updated.device_id && !interfacesByDevice[updated.device_id]) {
      api.getDeviceInterfaces(updated.device_id).then((ifs) =>
        setInterfacesByDevice((prev) => ({ ...prev, [updated.device_id]: ifs }))
      ).catch(() => {});
    }
  };

  const removeNode = async (nodeId) => {
    await api.deleteDiagramNode(nodeId);
    setNodes((prev) => prev.filter((n) => n.node_id !== nodeId));
    setEdges((prev) => prev.filter((e) => e.node_a !== nodeId && e.node_b !== nodeId));
    setSelectedNode(null);
  };

  const removeEdge = async (edgeId) => {
    await api.deleteDiagramEdge(edgeId);
    setEdges((prev) => prev.filter((e) => e.edge_id !== edgeId));
  };

  const setEdgeInterface = async (edge, side, ifName) => {
    // No PATCH endpoint for edges -- delete and recreate with the new interface.
    await api.deleteDiagramEdge(edge.edge_id);
    const created = await api.createDiagramEdge({
      node_a: edge.node_a, node_b: edge.node_b,
      interface_a: side === "a" ? ifName : edge.interface_a,
      interface_b: side === "b" ? ifName : edge.interface_b,
    });
    setEdges((prev) => [...prev.filter((e) => e.edge_id !== edge.edge_id), created]);
  };

  const nodeById = (id) => nodes.find((n) => n.node_id === id);
  const deviceName = (id) => devices.find((d) => d.device_id === id)?.hostname;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Network Diagram</h1>
          <p>Draw your real topology — WiFi, switches, routers, firewalls, ISP — and map each icon to an onboarded device and interface.</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-muted)" }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: connected ? "var(--good)" : "var(--warn)" }} />
            {connected ? "Live" : "Reconnecting…"}
          </span>
          <button className={connecting ? "btn-primary" : "btn-ghost"} onClick={() => { setConnecting(!connecting); setConnectFrom(null); }}>
            <Link2 size={14} /> {connecting ? "Click two icons to connect…" : "Connect"}
          </button>
        </div>
      </div>

      <Card>
        <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
          {nodeTypes.map((t) => {
            const Icon = ICONS[t.type] || Box;
            return (
              <button key={t.type} className="btn-ghost" onClick={() => addNode(t.type)}>
                <Icon size={14} /> {t.label}
              </button>
            );
          })}
        </div>

        <div style={{ display: "flex", gap: 16, marginBottom: 12, flexWrap: "wrap", fontSize: 11.5, color: "var(--text-muted)" }}>
          <span style={{ fontWeight: 600, color: "var(--text-faint)", textTransform: "uppercase", fontSize: 10.5 }}>Links</span>
          {[["Up", "var(--good)"], ["Down", "var(--bad)"], ["Warning", "var(--warn)"], ["Unknown / Admin Down", "var(--text-faint)"]].map(([label, color]) => (
            <span key={label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 14, height: 2, background: color, display: "inline-block" }} /> {label}
            </span>
          ))}
          <span style={{ fontWeight: 600, color: "var(--text-faint)", textTransform: "uppercase", fontSize: 10.5, marginLeft: 8 }}>Alarms</span>
          {["critical", "high", "medium", "low", "information"].map((sev) => (
            <span key={sev} style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: SEVERITY_COLOR[sev], display: "inline-block" }} /> {SEVERITY_LABEL[sev]}
            </span>
          ))}
        </div>

        <div style={{ display: "flex", gap: 16 }}>
          <div style={{ position: "relative", flex: 1 }}>
          <svg
            ref={svgRef}
            width="100%" height="520" viewBox="0 0 900 520"
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, width: "100%" }}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
          >
            {edges.map((e) => {
              const a = nodeById(e.node_a), b = nodeById(e.node_b);
              if (!a || !b) return null;
              const x1 = a.pos_x + NODE_W / 2, y1 = a.pos_y + NODE_H / 2;
              const x2 = b.pos_x + NODE_W / 2, y2 = b.pos_y + NODE_H / 2;
              const cls = edgeClassification(status, a, b, e);
              const stroke = cls ? LINK_COLOR[cls] : "var(--text-faint)";
              const dash = cls ? LINK_DASH[cls] : undefined;
              return (
                <g key={e.edge_id} style={{ cursor: "pointer" }} onClick={() => removeEdge(e.edge_id)}>
                  <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={stroke} strokeWidth={cls === "down" ? 2.5 : 1.5}
                        strokeDasharray={dash} style={{ transition: "stroke 0.3s" }} />
                  <circle cx={(x1 + x2) / 2} cy={(y1 + y2) / 2} r="7" fill="var(--surface-2)" stroke="var(--border)" />
                </g>
              );
            })}
            {nodes.map((n) => {
              const Icon = ICONS[n.node_type] || Box;
              const isSelected = selectedNode?.node_id === n.node_id;
              const isConnectSource = connectFrom === n.node_id;
              const devStatus = n.device_id ? status.devices?.[n.device_id] : null;
              const alarmCount = devStatus?.alarm_count || 0;
              const dotColor = n.device_id ? (DEVICE_STATUS_COLOR[devStatus?.status] || "var(--text-faint)") : null;
              return (
                <g key={n.node_id} transform={`translate(${n.pos_x},${n.pos_y})`}
                   style={{ cursor: connecting ? "crosshair" : "grab" }}
                   onMouseDown={(evt) => onNodeMouseDown(n, evt)}
                   onClick={() => onNodeClick(n)}>
                  <rect width={NODE_W} height={NODE_H} rx="8"
                        fill="var(--surface)" stroke={isSelected || isConnectSource ? "var(--accent)" : "var(--border)"}
                        strokeWidth={isSelected || isConnectSource ? 2 : 1} />
                  <foreignObject x="8" y="8" width="20" height="20">
                    <Icon size={18} color="var(--text-muted)" />
                  </foreignObject>
                  <text x={NODE_W / 2} y={NODE_H - 10} textAnchor="middle" fontSize="11" fill="var(--text)">
                    {n.label.length > 14 ? n.label.slice(0, 13) + "…" : n.label}
                  </text>
                  {/* Live device-health dot: green while ok, recolors to the worst active alarm's tone. Small and out of the way, same spot the old static "mapped" dot used. */}
                  {n.device_id && <circle cx={NODE_W - 10} cy="10" r="4" fill={dotColor} style={{ transition: "fill 0.3s" }} />}
                  {/* Alarm badge: only appears when there's something active, never obstructs the icon/label. Hover = quick tooltip, click = full alarm list. */}
                  {alarmCount > 0 && (
                    <g
                      transform="translate(-8,-8)"
                      style={{ cursor: "pointer" }}
                      onMouseEnter={(evt) => {
                        const rect = svgRef.current.getBoundingClientRect();
                        setHoverAlarms({ nodeId: n.node_id, x: evt.clientX - rect.left, y: evt.clientY - rect.top });
                      }}
                      onMouseLeave={() => setHoverAlarms((h) => (h?.nodeId === n.node_id ? null : h))}
                      onClick={(evt) => { evt.stopPropagation(); setAlarmModalNode(n); }}
                    >
                      <circle r="9" fill={SEVERITY_COLOR[devStatus.alarms[0]?.severity] || "var(--bad)"} stroke="var(--surface)" strokeWidth="2" />
                      <text textAnchor="middle" dy="3.5" fontSize="10" fontWeight="700" fill="#14110A">
                        {alarmCount > 9 ? "9+" : alarmCount}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>

          {hoverAlarms && status.devices?.[nodeById(hoverAlarms.nodeId)?.device_id] && (() => {
            const n = nodeById(hoverAlarms.nodeId);
            const dev = status.devices[n.device_id];
            const top = dev.alarms[0];
            return (
              <div style={{
                position: "absolute", left: hoverAlarms.x + 12, top: hoverAlarms.y + 12, zIndex: 20,
                background: "var(--surface-3)", border: "1px solid var(--border)", borderRadius: 8,
                padding: "10px 12px", width: 240, fontSize: 12, boxShadow: "0 6px 20px rgba(0,0,0,0.35)",
                pointerEvents: "none",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: SEVERITY_COLOR[top.severity] }} />
                  <strong>{top.severity_label}</strong>
                  <span style={{ color: "var(--text-faint)" }}>· {top.name}</span>
                </div>
                <div style={{ color: "var(--text-muted)", marginBottom: 4 }}>{top.description}</div>
                <div style={{ color: "var(--text-faint)", fontSize: 11 }}>
                  {new Date(top.triggered_at).toLocaleString()}
                  {top.interface ? ` · ${top.interface}` : ""}
                </div>
                {dev.alarm_count > 1 && (
                  <div style={{ marginTop: 6, color: "var(--accent)", fontSize: 11 }}>
                    +{dev.alarm_count - 1} more — click for all active alarms
                  </div>
                )}
              </div>
            );
          })()}
          </div>

          <div style={{ width: 260, flexShrink: 0 }}>
            {!selectedNode ? (
              <div className="empty-state" style={{ padding: "20px 0" }}>
                <p>Click an icon on the canvas to rename it, map it to an onboarded device, or delete it. Click "Connect" then two icons to draw a link. Click a link to remove it.</p>
              </div>
            ) : (
              <div>
                <div className="filter-field" style={{ marginBottom: 10 }}>
                  <label>Label</label>
                  <input value={selectedNode.label} onChange={(e) => setSelectedNode({ ...selectedNode, label: e.target.value })}
                         onBlur={(e) => saveNodeEdit({ label: e.target.value })} />
                </div>
                <div className="filter-field" style={{ marginBottom: 10 }}>
                  <label>Mapped Device</label>
                  <select value={selectedNode.device_id || ""} onChange={(e) => saveNodeEdit({ device_id: e.target.value || null })}>
                    <option value="">— Unmanaged / external —</option>
                    {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.hostname}</option>)}
                  </select>
                </div>
                {selectedNode.device_id && (
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 10 }}>
                    Mapped to {deviceName(selectedNode.device_id)} — its interfaces are now selectable on any link connected to this icon below.
                  </div>
                )}
                <button className="btn-ghost" onClick={() => removeNode(selectedNode.node_id)} style={{ color: "var(--bad)" }}>
                  <Trash2 size={14} /> Delete Icon
                </button>

                <div style={{ height: 16 }} />
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 8 }}>Links</div>
                {edges.filter((e) => e.node_a === selectedNode.node_id || e.node_b === selectedNode.node_id).map((e) => {
                  const other = nodeById(e.node_a === selectedNode.node_id ? e.node_b : e.node_a);
                  const mySide = e.node_a === selectedNode.node_id ? "a" : "b";
                  const myIf = mySide === "a" ? e.interface_a : e.interface_b;
                  const options = selectedNode.device_id ? (interfacesByDevice[selectedNode.device_id] || []) : [];
                  return (
                    <div key={e.edge_id} style={{ fontSize: 12.5, padding: "8px 0", borderTop: "1px solid var(--border)" }}>
                      <div>↔ {other?.label || "?"}</div>
                      {selectedNode.device_id ? (
                        <select value={myIf || ""} onChange={(ev) => setEdgeInterface(e, mySide, ev.target.value || null)} style={{ marginTop: 4, width: "100%" }}>
                          <option value="">Select interface…</option>
                          {options.map((i) => <option key={i.if_name} value={i.if_name}>{i.if_name}</option>)}
                        </select>
                      ) : (
                        <div style={{ color: "var(--text-faint)", marginTop: 2 }}>No interface (unmanaged icon)</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </Card>

      <Modal
        open={!!alarmModalNode}
        onClose={() => setAlarmModalNode(null)}
        title={alarmModalNode ? `Active Alarms — ${alarmModalNode.label}` : ""}
      >
        {alarmModalNode && (() => {
          const dev = status.devices?.[alarmModalNode.device_id];
          if (!dev || dev.alarms.length === 0) return <p style={{ color: "var(--text-muted)" }}>No active alarms.</p>;
          return (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {dev.alarms.map((a) => (
                <div key={a.alarm_id} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: SEVERITY_COLOR[a.severity] }} />
                    <strong style={{ fontSize: 13 }}>{a.severity_label}</strong>
                    <span style={{ color: "var(--text-faint)", fontSize: 12.5 }}>· {a.name}</span>
                  </div>
                  <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 4 }}>{a.description}</div>
                  <div style={{ fontSize: 11.5, color: "var(--text-faint)" }}>
                    Generated {new Date(a.triggered_at).toLocaleString()}
                    {a.interface ? ` · Interface ${a.interface}` : ""}
                  </div>
                </div>
              ))}
            </div>
          );
        })()}
      </Modal>
    </div>
  );
}
