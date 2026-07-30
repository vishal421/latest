// Reuses the same real /topology/graph data and auto-layering logic
// as before, restyled for the enterprise brief: flat status colors,
// thin connecting lines, no glow/blur, minimal motion (a subtle
// opacity pulse on active links only, nothing louder).

function layoutTopology(nodes, links) {
  const nodeIds = nodes.map((n) => n.device_id);
  const incoming = {}; const outgoing = {};
  nodeIds.forEach((id) => { incoming[id] = []; outgoing[id] = []; });
  links.forEach((l) => {
    if (outgoing[l.device_a]) outgoing[l.device_a].push(l.device_b);
    if (incoming[l.device_b]) incoming[l.device_b].push(l.device_a);
  });

  const layer = {};
  let frontier = nodeIds.filter((id) => incoming[id].length === 0);
  frontier.forEach((id) => (layer[id] = 0));
  const visited = new Set(frontier);
  let depth = 0;
  while (frontier.length > 0 && depth < nodeIds.length) {
    depth += 1;
    const next = [];
    frontier.forEach((id) => {
      (outgoing[id] || []).forEach((child) => {
        const candidate = (layer[id] || 0) + 1;
        if (layer[child] === undefined || candidate > layer[child]) layer[child] = candidate;
        if (!visited.has(child)) { visited.add(child); next.push(child); }
      });
    });
    frontier = next;
  }
  nodeIds.forEach((id) => { if (layer[id] === undefined) layer[id] = 0; });

  const byLayer = {};
  nodeIds.forEach((id) => {
    const l = layer[id];
    byLayer[l] = byLayer[l] || [];
    byLayer[l].push(id);
  });

  const colWidth = 190, rowHeight = 84, padX = 90, padY = 50;
  const positions = {};
  Object.keys(byLayer).sort((a, b) => a - b).forEach((l) => {
    byLayer[l].forEach((id, i) => {
      positions[id] = { x: padX + Number(l) * colWidth, y: padY + i * rowHeight };
    });
  });
  const maxLayer = Math.max(0, ...Object.keys(byLayer).map(Number));
  const maxRows = Math.max(1, ...Object.values(byLayer).map((arr) => arr.length));
  return { positions, width: padX * 2 + maxLayer * colWidth, height: padY * 2 + (maxRows - 1) * rowHeight };
}

function linkStatus(status) {
  if (status.admin_status === "disabled") return "disabled";
  if (status.oper_status === "down") return "down";
  if (status.oper_status === "up") return "up";
  return "unknown";
}

export default function TopologyView({ nodes, links, highlightIds }) {
  if (!nodes || nodes.length === 0) {
    return <div className="topology-empty">No devices onboarded yet.</div>;
  }
  const { positions, width, height } = layoutTopology(nodes, links);
  const boxW = 148, boxH = 48;
  const highlightSet = new Set(highlightIds || []);

  return (
    <div className="topology-outer">
      <svg width="100%" height={Math.max(height, 220)} viewBox={`0 0 ${width} ${height}`}>
        {links.map((l, i) => {
          const a = positions[l.device_a], b = positions[l.device_b];
          if (!a || !b) return null;
          const x1 = a.x + boxW, y1 = a.y + boxH / 2, x2 = b.x, y2 = b.y + boxH / 2;
          const statusA = linkStatus(l.a_status), statusB = linkStatus(l.b_status);
          const worst = [statusA, statusB].includes("disabled") ? "disabled" : [statusA, statusB].includes("down") ? "down" : "up";
          const colorVar = worst === "up" ? "var(--good)" : worst === "down" ? "var(--bad)" : "var(--text-faint)";
          const onPath = highlightSet.has(l.device_a) && highlightSet.has(l.device_b);
          return (
            <g key={i}>
              {onPath && <line x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth="5" stroke="var(--accent)" opacity="0.18" />}
              <line x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth="1.5" stroke={colorVar}
                    strokeDasharray={worst === "disabled" ? "4 4" : undefined} />
            </g>
          );
        })}
        {nodes.map((n) => {
          const p = positions[n.device_id];
          if (!p) return null;
          const traced = highlightSet.has(n.device_id);
          return (
            <g key={n.device_id} transform={`translate(${p.x},${p.y})`}>
              {traced && <rect x="-3" y="-3" width={boxW + 6} height={boxH + 6} rx="9" fill="none" stroke="var(--accent)" strokeWidth="1.5" />}
              <rect width={boxW} height={boxH} rx="7" fill="var(--surface-2)" stroke="var(--border)" />
              <circle cx="14" cy="14" r="4" fill="var(--good)" />
              <text x="26" y="18" fill="var(--text)" fontFamily="var(--font-mono)" fontSize="11">{n.hostname}</text>
              <text x="12" y="35" fill="var(--text-muted)" fontFamily="var(--font-mono)" fontSize="9" letterSpacing="0.04em">
                {n.device_type.toUpperCase()} · {n.vendor}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="topology-legend">
        <span><i className="legend-dot" style={{ background: "var(--good)" }} />Up</span>
        <span><i className="legend-dot" style={{ background: "var(--bad)" }} />Down</span>
        <span><i className="legend-dot" style={{ background: "var(--text-faint)" }} />Disabled</span>
      </div>
    </div>
  );
}
