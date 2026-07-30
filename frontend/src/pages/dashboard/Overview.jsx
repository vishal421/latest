import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Card from "../../components/Card";
import DataTable from "../../components/DataTable";
import StatusBadge from "../../components/StatusBadge";
import MockBadge from "../../components/MockBadge";
import TopologyView from "../../components/TopologyView";
import DeviceHealthTable from "../../components/DeviceHealthTable";
import { api } from "../../api";

function formatBytes(n) {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

export default function Overview() {
  const [deviceCount, setDeviceCount] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], links: [] });
  const [alarmSummary, setAlarmSummary] = useState(null);
  const [alarms, setAlarms] = useState([]);
  const [licenses, setLicenses] = useState([]);
  const [trafficTotal, setTrafficTotal] = useState(null);

  useEffect(() => {
    api.listDevices().then((d) => setDeviceCount(d.length)).catch(() => setDeviceCount(0));
    api.getTopologyGraph().then(setGraph).catch(() => {});
    api.getAlarmsSummary().then(setAlarmSummary).catch(() => {});
    api.listAlarms({ limit: "10" }).then(setAlarms).catch(() => {});
    api.listLicenses().then(setLicenses).catch(() => {});
    api.getTrafficAnalytics({ since_minutes: "60" }).then((d) => setTrafficTotal(d.total_bytes)).catch(() => {});
  }, []);

  const expiringLicenses = licenses.filter((l) => l.remaining_days != null && l.remaining_days <= 30);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Overview</h1>
          <p>Network and security posture across every onboarded device.</p>
        </div>
      </div>

      {/* Section 1 — Summary cards */}
      <div className="card-grid">
        <Card className="stat-card">
          <div className="stat-label">Total Devices</div>
          <div className="stat-value">{deviceCount ?? "—"}</div>
        </Card>
        <Card className="stat-card stat-good">
          <div className="stat-label">Healthy Devices</div>
          <div className="stat-value">{deviceCount ?? "—"}</div>
          <div className="stat-sub">based on last poll</div>
        </Card>
        <Card className="stat-card stat-bad">
          <div className="stat-label">Critical Devices</div>
          <div className="stat-value">{alarmSummary?.critical ?? "—"}</div>
          <div className="stat-sub">devices with a critical alarm</div>
        </Card>
        <Card className="stat-card stat-warn">
          <div className="stat-label">Active Alarms</div>
          <div className="stat-value">{alarmSummary?.active_total ?? "—"}</div>
        </Card>
        <Card className="stat-card">
          <div className="stat-label">Total Traffic</div>
          <div className="stat-value">
            {trafficTotal == null ? "—" : formatBytes(trafficTotal)}
          </div>
          <div className="stat-sub">last 60 minutes</div>
        </Card>
        <Card className="stat-card">
          <div className="stat-label">Active VPN</div>
          <div className="stat-value">3</div>
          <MockBadge />
        </Card>
        <Card className="stat-card stat-warn">
          <div className="stat-label">License Expiry</div>
          <div className="stat-value">{expiringLicenses.length}</div>
          <div className="stat-sub">within 30 days</div>
        </Card>
        <Card className="stat-card">
          <div className="stat-label">Configuration Changes</div>
          <div className="stat-value">7</div>
          <div className="stat-sub">last 24h</div>
          <MockBadge />
        </Card>
      </div>

      {/* Section 2 — Network topology preview */}
      <Card title="Network Topology" action={<Link to="/dashboard/topology" className="btn-ghost">View full topology</Link>}>
        <TopologyView nodes={graph.nodes} links={graph.links} />
      </Card>

      <div style={{ height: 20 }} />

      {/* Section 3 — Device health preview */}
      <Card title="Device Health" action={<Link to="/dashboard/health" className="btn-ghost">View all</Link>}>
        <DeviceHealthTable limit={5} />
      </Card>

      <div style={{ height: 20 }} />

      <div className="grid-2col">
        {/* Section 4 — Alarms (real, generated from real polled thresholds) */}
        <Card title="Active / Past Alarms">
          <DataTable
            columns={[
              { key: "severity", label: "Severity", render: (r) => <StatusBadge status={r.severity} /> },
              { key: "device_id", label: "Device" },
              { key: "triggered_at", label: "Time", render: (r) => new Date(r.triggered_at).toLocaleString() },
              { key: "description", label: "Description" },
              { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> },
            ]}
            rows={alarms}
            emptyLabel="No alarms — every polled device is within threshold."
          />
        </Card>

        {/* Section 5 — License status (real, pulled from onboarded firewalls) */}
        <Card title="License Status">
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {licenses.length === 0 && <div className="empty" style={{ color: "var(--text-faint)", fontSize: 13 }}>No license data yet — onboard a Palo Alto or Fortigate firewall.</div>}
            {licenses.map((l, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "10px 12px", borderRadius: 8,
                background: l.remaining_days != null && l.remaining_days <= 30 ? "var(--warn-soft)" : "var(--surface-2)",
                border: "1px solid var(--border)",
              }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{l.feature}</div>
                  <div style={{ fontSize: 11.5, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                    {l.device_id} · {l.expiry_date ? `expires ${new Date(l.expiry_date).toLocaleDateString()}` : "no expiry"}
                  </div>
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: l.remaining_days != null && l.remaining_days <= 30 ? "var(--warn)" : "var(--text-muted)" }}>
                  {l.remaining_days != null ? `${l.remaining_days}d` : "—"}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
