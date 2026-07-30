import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import Card from "../../components/Card";
import DataTable from "../../components/DataTable";
import { chartColor, gridColor } from "../../components/BarWidget";
import { api } from "../../api";

// Real, current per-interface Tx/Rx, plus a real bandwidth-over-time
// trend for whichever interface is busiest right now -- sampled every
// ~60s (see app/link_stats.py), not synthesized.
export default function LinkUtilization() {
  const [rows, setRows] = useState([]);
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const devices = await api.listDevices();
        const perDevice = await Promise.all(
          devices.map(async (d) => {
            const interfaces = await api.listDeviceInterfaces(d.device_id).catch(() => []);
            return interfaces.map((i) => ({ ...i, device: d.hostname, device_id: d.device_id }));
          })
        );
        const flat = perDevice.flat().filter((i) => i.tx_mbps != null || i.rx_mbps != null);
        flat.sort((a, b) => ((b.tx_mbps || 0) + (b.rx_mbps || 0)) - ((a.tx_mbps || 0) + (a.rx_mbps || 0)));
        setRows(flat);
        if (flat.length > 0) setSelected(flat[0]);
      } catch (err) { setError(err.message); }
    })();
  }, []);

  useEffect(() => {
    if (!selected) return;
    api.getInterfaceHistory(selected.device_id, { if_name: selected.if_name, since_minutes: "180" })
      .then((h) => setHistory(h.map((p) => ({ ...p, time: new Date(p.timestamp).toLocaleTimeString() }))))
      .catch(() => setHistory([]));
  }, [selected]);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Link Utilization</h1>
          <p>Real current Tx/Rx per interface, plus a real bandwidth trend (sampled every ~60s) for whichever you select below.</p>
        </div>
      </div>
      {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

      {selected && (
        <Card title={`Bandwidth trend — ${selected.device} · ${selected.if_name}`}>
          {history.length < 2 ? (
            <div className="empty" style={{ color: "var(--text-faint)", fontSize: 13, padding: "20px 0" }}>
              Not enough history yet — samples accumulate every ~60 seconds. Check back shortly.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={history}>
                <CartesianGrid stroke={gridColor} vertical={false} />
                <XAxis dataKey="time" stroke="#8992A3" fontSize={11} />
                <YAxis stroke="#8992A3" fontSize={11} label={{ value: "Mbps", angle: -90, position: "insideLeft", fill: "#8992A3", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#171C24", border: "1px solid #232A35", fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="tx_mbps" name="Tx Mbps" stroke={chartColor} strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="rx_mbps" name="Rx Mbps" stroke="#33C48D" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
      )}

      <div style={{ height: 20 }} />
      <Card title="All interfaces (click a row to chart its trend)">
        <DataTable
          columns={[
            { key: "device", label: "Device" },
            { key: "if_name", label: "Interface" },
            { key: "oper_status", label: "Status" },
            { key: "tx_mbps", label: "Tx Mbps", render: (r) => r.tx_mbps != null ? r.tx_mbps.toFixed(2) : "—" },
            { key: "rx_mbps", label: "Rx Mbps", render: (r) => r.rx_mbps != null ? r.rx_mbps.toFixed(2) : "—" },
          ]}
          rows={rows}
          onRowClick={setSelected}
          emptyLabel="No live interface data yet — give the poller a moment after onboarding a Cisco or Fortigate device (Palo Alto doesn't report Tx/Rx counters yet, see README)."
        />
      </Card>
    </div>
  );
}
