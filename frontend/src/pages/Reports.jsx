import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import Card from "../components/Card";
import { api } from "../api";

function formatBytes(n) {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

export default function Reports() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [windowMinutes, setWindowMinutes] = useState("1440");

  const load = () => {
    api.getReportSummary({ since_minutes: windowMinutes }).then(setReport).catch((e) => setError(e.message));
  };
  useEffect(load, [windowMinutes]);

  const download = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `infraos-report-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Reports</h1>
          <p>A real summary assembled from every other module — devices, alarms, licenses, and traffic. No separate data source; this is aggregation, not generation.</p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
          <div>
            <label>Window</label>
            <select value={windowMinutes} onChange={(e) => setWindowMinutes(e.target.value)}>
              <option value="60">Last hour</option>
              <option value="1440">Last 24 hours</option>
              <option value="10080">Last 7 days</option>
            </select>
          </div>
          <button className="btn-ghost" onClick={download}><Download size={14} /> Export JSON</button>
        </div>
      </div>
      {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

      {report && (
        <>
          <div className="card-grid">
            <Card className="stat-card">
              <div className="stat-label">Devices</div>
              <div className="stat-value">{report.devices.total}</div>
              <div className="stat-sub">{Object.entries(report.devices.by_vendor).map(([v, c]) => `${v}: ${c}`).join(", ") || "none onboarded"}</div>
            </Card>
            <Card className={`stat-card ${report.alarms.currently_active > 0 ? "stat-bad" : "stat-good"}`}>
              <div className="stat-label">Active Alarms</div>
              <div className="stat-value">{report.alarms.currently_active}</div>
              <div className="stat-sub">{report.alarms.active_critical} critical, {report.alarms.active_high} high</div>
            </Card>
            <Card className={`stat-card ${report.licenses.expiring_within_30_days.length > 0 ? "stat-warn" : ""}`}>
              <div className="stat-label">Licenses Expiring Soon</div>
              <div className="stat-value">{report.licenses.expiring_within_30_days.length}</div>
              <div className="stat-sub">of {report.licenses.total_tracked} tracked</div>
            </Card>
            <Card className={`stat-card ${report.traffic.denied_count > 0 ? "stat-warn" : ""}`}>
              <div className="stat-label">Denied Traffic</div>
              <div className="stat-value">{report.traffic.denied_count}</div>
              <div className="stat-sub">flows in this window</div>
            </Card>
          </div>

          <div className="grid-2col">
            <Card title="Traffic Summary">
              <div style={{ fontSize: 13, marginBottom: 10 }}>
                <strong>{formatBytes(report.traffic.total_bytes)}</strong> total traffic, <strong>{report.traffic.denied_count}</strong> denied flows in this window.
              </div>
              {report.traffic.top_applications.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {report.traffic.top_applications.map((a, i) => (
                    <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, fontFamily: "var(--font-mono)" }}>
                      <span>{a.key}</span><span style={{ color: "var(--text-muted)" }}>{formatBytes(a.bytes_total)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
            <Card title="Licenses Expiring Within 30 Days">
              {report.licenses.expiring_within_30_days.length === 0 ? (
                <div className="empty" style={{ color: "var(--text-faint)", fontSize: 13 }}>None.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {report.licenses.expiring_within_30_days.map((l, i) => (
                    <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, fontFamily: "var(--font-mono)" }}>
                      <span>{l.feature}</span><span style={{ color: "var(--warn)" }}>{new Date(l.expiry_date).toLocaleDateString()}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 16 }}>
            Generated {new Date(report.generated_at).toLocaleString()}
          </div>
        </>
      )}
    </div>
  );
}
