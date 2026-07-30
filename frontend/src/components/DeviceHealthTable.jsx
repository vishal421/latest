import { useEffect, useState } from "react";
import DataTable from "./DataTable";
import StatusBadge from "./StatusBadge";
import { api } from "../api";

function healthStatusFor(snapshot) {
  if (!snapshot) return "Unknown";
  if ((snapshot.cpu_pct ?? 0) > 85 || (snapshot.memory_pct ?? 0) > 90) return "Critical";
  if ((snapshot.cpu_pct ?? 0) > 65 || (snapshot.memory_pct ?? 0) > 75) return "Warning";
  return "Healthy";
}

export default function DeviceHealthTable({ limit }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const devices = await api.listDevices();
        const withHealth = await Promise.all(
          devices.map(async (d) => {
            let latest = null;
            try {
              const history = await api.getHealthHistory(d.device_id);
              latest = history[history.length - 1] || null;
            } catch { /* device unreachable, health just shows unknown */ }
            return { ...d, health: latest };
          })
        );
        if (!cancelled) setRows(limit ? withHealth.slice(0, limit) : withHealth);
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [limit]);

  const columns = [
    { key: "hostname", label: "Device" },
    { key: "vendor", label: "Vendor" },
    { key: "mgmt_ip", label: "Management IP" },
    { key: "status", label: "Status", render: (r) => <StatusBadge status={healthStatusFor(r.health)} /> },
    { key: "cpu", label: "CPU", render: (r) => (r.health?.cpu_pct != null ? `${r.health.cpu_pct}%` : "—") },
    { key: "memory", label: "Memory", render: (r) => (r.health?.memory_pct != null ? `${r.health.memory_pct}%` : "—") },
    { key: "temperature", label: "Temperature", render: () => "—" }, // not exposed by any driver yet
    { key: "uptime", label: "Uptime", render: (r) => (r.health?.uptime_seconds != null ? `${Math.round(r.health.uptime_seconds / 3600)}h` : "—") },
    { key: "os_version", label: "Software Version" },
  ];

  if (loading) return <div className="empty-state" style={{ padding: "32px 0" }}><p>Loading device health…</p></div>;
  if (error) return <div className="empty-state" style={{ padding: "32px 0" }}><p style={{ color: "var(--bad)" }}>{error}</p></div>;

  return <DataTable columns={columns} rows={rows} emptyLabel="No devices onboarded yet." />;
}
