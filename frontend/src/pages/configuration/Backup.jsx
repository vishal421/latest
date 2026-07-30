import { useEffect, useState } from "react";
import { Download, Play } from "lucide-react";
import Card from "../../components/Card";
import DataTable from "../../components/DataTable";
import StatusBadge from "../../components/StatusBadge";
import Modal from "../../components/Modal";
import { api } from "../../api";

export default function Backup() {
  const [backups, setBackups] = useState([]);
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [viewing, setViewing] = useState(null); // { backup_id, content } | null

  const load = () => api.listConfigBackups().then(setBackups).catch((e) => setError(e.message));
  useEffect(() => {
    load();
    api.listDevices().then(setDevices).catch(() => {});
  }, []);

  const runBackup = async () => {
    if (!deviceId) { setError("Select a device first."); return; }
    setRunning(true); setError(null);
    try {
      await api.pollConfigBackupNow(deviceId);
      await load();
    } catch (err) { setError(err.message); }
    finally { setRunning(false); }
  };

  const viewContent = async (backup) => {
    try {
      const res = await api.getConfigBackupContent(backup.backup_id);
      setViewing(res);
    } catch (err) { setError(err.message); }
  };

  const hostnameFor = (id) => (devices.find((d) => d.device_id === id) || {}).hostname || id;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Configuration Backup</h1>
          <p>Real configuration snapshots pulled directly from each device (PAN-OS/FortiOS/Cisco IOS). Polled daily, or run on demand below.</p>
        </div>
      </div>

      <Card title="Run a backup now">
        <div className="grid-2col" style={{ alignItems: "flex-end" }}>
          <div>
            <label>Device</label>
            <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
              <option value="">Select…</option>
              {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.hostname} ({d.vendor})</option>)}
            </select>
          </div>
          <button className="btn-primary" onClick={runBackup} disabled={running}>
            <Play size={14} style={{ marginRight: 6, verticalAlign: "-2px" }} />
            {running ? "Running…" : "Run backup"}
          </button>
        </div>
        {error && <div style={{ color: "var(--bad)", fontSize: 13, marginTop: 10 }}>{error}</div>}
      </Card>

      <div style={{ height: 20 }} />
      <Card title="Backup history">
        <DataTable
          columns={[
            { key: "device_id", label: "Device", render: (r) => hostnameFor(r.device_id) },
            { key: "taken_at", label: "Taken At", render: (r) => new Date(r.taken_at).toLocaleString() },
            { key: "size_bytes", label: "Size", render: (r) => r.size_bytes ? `${(r.size_bytes / 1024).toFixed(1)} KB` : "—" },
            { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> },
            {
              key: "actions", label: "Actions",
              render: (r) => r.status === "success" ? (
                <button className="icon-btn" title="View config" onClick={() => viewContent(r)}><Download size={14} /></button>
              ) : <span style={{ fontSize: 11.5, color: "var(--bad)" }}>{r.error}</span>,
            },
          ]}
          rows={backups}
          emptyLabel="No backups yet — run one above, or wait for the daily scheduled backup."
        />
      </Card>

      <Modal open={!!viewing} onClose={() => setViewing(null)} title={`Config — backup #${viewing?.backup_id ?? ""}`}>
        <pre style={{
          maxHeight: "50vh", overflow: "auto", fontFamily: "var(--font-mono)", fontSize: 11.5,
          whiteSpace: "pre-wrap", color: "var(--text)", margin: 0,
        }}>
          {viewing?.content}
        </pre>
      </Modal>
    </div>
  );
}
