import { useEffect, useState } from "react";
import { Save, Upload, Eye, GitCompare } from "lucide-react";
import Card from "../../components/Card";
import DataTable from "../../components/DataTable";
import Modal from "../../components/Modal";
import StatusBadge from "../../components/StatusBadge";
import { api } from "../../api";

function AddDeviceForm({ onAdded }) {
  const [form, setForm] = useState({
    hostname: "", mgmt_ip: "", vendor: "paloalto", device_type: "firewall",
    username: "admin", password: "", api_key: "",
  });
  const [status, setStatus] = useState(null);
  const update = (k) => (e) => {
    const next = { ...form, [k]: e.target.value };
    if (k === "vendor") next.device_type = e.target.value === "cisco_ios" ? "router" : "firewall";
    setForm(next);
  };

  const submit = async (e) => {
    e.preventDefault();
    setStatus("saving");
    try {
      await api.addDevice(form);
      setStatus("ok");
      onAdded();
      setForm({ ...form, hostname: "", mgmt_ip: "", password: "", api_key: "" });
    } catch (err) { setStatus("error:" + err.message); }
  };

  return (
    <form onSubmit={submit}>
      <div className="grid-2col">
        <div><label>Hostname</label><input required value={form.hostname} onChange={update("hostname")} placeholder="edge-fw-01" /></div>
        <div><label>Management IP</label><input required value={form.mgmt_ip} onChange={update("mgmt_ip")} placeholder="10.0.0.1" /></div>
        <div>
          <label>Vendor</label>
          <select value={form.vendor} onChange={update("vendor")}>
            <option value="paloalto">Palo Alto (PAN-OS)</option>
            <option value="fortigate">Fortigate (FortiOS)</option>
            <option value="cisco_ios">Cisco IOS</option>
          </select>
        </div>
        <div>
          <label>Device type</label>
          {form.vendor === "cisco_ios" ? (
            <select value={form.device_type} onChange={update("device_type")}>
              <option value="router">Router</option>
              <option value="switch">Switch</option>
            </select>
          ) : <select value="firewall" disabled><option>Firewall</option></select>}
        </div>
        <div><label>Username</label><input value={form.username} onChange={update("username")} /></div>
        <div>
          <label>Password / API Key</label>
          <input type="password" value={form.vendor === "fortigate" ? form.api_key : form.password}
                 onChange={update(form.vendor === "fortigate" ? "api_key" : "password")} />
        </div>
      </div>
      <button className="btn-primary" type="submit" disabled={status === "saving"}>
        {status === "saving" ? "Onboarding…" : "Onboard device"}
      </button>
      {status && status.startsWith("error") && <div style={{ color: "var(--bad)", fontSize: 12.5, marginTop: 8 }}>{status.slice(6)}</div>}
    </form>
  );
}

export default function Devices() {
  const [devices, setDevices] = useState([]);
  const [error, setError] = useState(null);
  const [viewConfigFor, setViewConfigFor] = useState(null);
  const [configContent, setConfigContent] = useState("");
  const [configLoading, setConfigLoading] = useState(false);
  const [configError, setConfigError] = useState(null);

  const load = () => api.listDevices().then(setDevices).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const backupNow = async (device) => {
    setError(null);
    try {
      const result = await api.pollConfigBackupNow(device.device_id);
      if (result.status !== "success") setError(`Backup failed for ${device.hostname}: ${result.error}`);
    } catch (err) { setError(err.message); }
  };

  const viewConfig = async (device) => {
    setViewConfigFor(device);
    setConfigLoading(true); setConfigError(null); setConfigContent("");
    try {
      const backups = await api.listConfigBackups({ device_id: device.device_id });
      const latestSuccess = backups.find((b) => b.status === "success");
      if (!latestSuccess) {
        setConfigContent("");
      } else {
        const res = await api.getConfigBackupContent(latestSuccess.backup_id);
        setConfigContent(res.content);
      }
    } catch (err) { setConfigError(err.message); }
    finally { setConfigLoading(false); }
  };

  return (
    <div>
      <div className="page-head">
        <div><h1>Devices</h1><p>Device inventory across every onboarded vendor.</p></div>
      </div>

      <Card title="Onboard a device">
        <AddDeviceForm onAdded={load} />
      </Card>

      <div style={{ height: 20 }} />
      <Card title="Device Inventory">
        {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 10 }}>{error}</div>}
        <DataTable
          columns={[
            { key: "vendor", label: "Vendor" },
            { key: "hostname", label: "Hostname" },
            { key: "mgmt_ip", label: "Management IP" },
            { key: "os_version", label: "Version" },
            { key: "model", label: "Model" },
            { key: "status", label: "Status", render: () => <StatusBadge status="Healthy" /> },
            {
              key: "actions", label: "Actions",
              render: (d) => (
                <div style={{ display: "flex", gap: 4 }}>
                  <button className="icon-btn" title="Backup config now" onClick={() => backupNow(d)}><Save size={14} /></button>
                  <button className="icon-btn" title="Push config (not yet built — see README on automated config-push)" disabled style={{ opacity: 0.4 }}><Upload size={14} /></button>
                  <button className="icon-btn" title="View last backed-up config" onClick={() => viewConfig(d)}><Eye size={14} /></button>
                  <button className="icon-btn" title="Configuration diff (not yet built)" disabled style={{ opacity: 0.4 }}><GitCompare size={14} /></button>
                </div>
              ),
            },
          ]}
          rows={devices}
          emptyLabel="No devices onboarded yet."
        />
      </Card>

      <Modal open={!!viewConfigFor} onClose={() => setViewConfigFor(null)} title={`Config — ${viewConfigFor?.hostname || ""}`}>
        {configLoading ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Loading…</div>
        ) : configError ? (
          <div style={{ fontSize: 13, color: "var(--bad)" }}>{configError}</div>
        ) : (
          <pre style={{
            maxHeight: "50vh", overflow: "auto", fontFamily: "var(--font-mono)", fontSize: 11.5,
            whiteSpace: "pre-wrap", color: "var(--text)", margin: 0,
          }}>
            {configContent || "No backup on file yet for this device — click the save icon to run one."}
          </pre>
        )}
      </Modal>
    </div>
  );
}
