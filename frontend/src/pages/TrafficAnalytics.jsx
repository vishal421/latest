import { useEffect, useState } from "react";
import Card from "../components/Card";
import BarWidget from "../components/BarWidget";
import { api } from "../api";

function formatBytes(n) {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

export default function TrafficAnalytics() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getTrafficAnalytics({ since_minutes: "60" }).then(setData).catch((e) => setError(e.message));
  }, []);

  const toChartData = (entries, keyLabel) => (entries || []).map((e) => ({ [keyLabel]: e.key, bytes: e.bytes_total }));

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Traffic Analytics</h1>
          <p>Real aggregation from logged traffic over the last {data?.since_minutes ?? 60} minutes — ranked by actual byte volume where the device reports it.</p>
        </div>
      </div>
      {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

      {data && data.top_source_ips.length === 0 && data.top_destination_ips.length === 0 && (
        <div className="ui-card">
          <div className="empty-state" style={{ padding: "50px 20px" }}>
            <h3>No traffic logs yet</h3>
            <p>This aggregates real traffic logs from onboarded firewalls — once logs are polled (every 2 minutes, or immediately after onboarding), top talkers and applications will populate here.</p>
          </div>
        </div>
      )}

      {data && (data.top_source_ips.length > 0 || data.top_destination_ips.length > 0) && (
        <>
          <div className="grid-2col">
            <BarWidget title="Top Source IPs (by bytes)" data={toChartData(data.top_source_ips, "ip")} xKey="ip" yKey="bytes" />
            <BarWidget title="Top Destination IPs (by bytes)" data={toChartData(data.top_destination_ips, "ip")} xKey="ip" yKey="bytes" />
          </div>
          <div style={{ height: 20 }} />
          <div className="grid-2col">
            <BarWidget title="Top Applications (by bytes)" data={toChartData(data.top_applications, "app")} xKey="app" yKey="bytes" />
            <Card title="Top Denied Destinations">
              {data.denied.length === 0 ? (
                <div className="empty" style={{ color: "var(--text-faint)", fontSize: 13 }}>No denied traffic logged in this window.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {data.denied.map((d, i) => (
                    <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, fontFamily: "var(--font-mono)", padding: "8px 0", borderBottom: i < data.denied.length - 1 ? "1px solid var(--border)" : "none" }}>
                      <span>{d.dst_ip}</span>
                      <span style={{ color: "var(--text-muted)" }}>{d.matched_rule}</span>
                      <span style={{ color: "var(--bad)" }}>{d.hits} hits</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
