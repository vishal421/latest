import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Download } from "lucide-react";
import Card from "../components/Card";
import FilterBar from "../components/FilterBar";
import DataTable from "../components/DataTable";
import { api } from "../api";

// Only Traffic Logs support search (source IP, destination IP, device).
// Every other log type is a plain live view of what's been collected
// for that type -- no filter fields, per the "search only on Traffic"
// requirement.
const TABS = [
  { key: "traffic", label: "Traffic" },
  { key: "threat", label: "Threat" },
  { key: "url", label: "URL" },
  { key: "system", label: "System" },
  { key: "sessions", label: "Sessions" },
];

const TRAFFIC_COLUMNS = [
  { key: "timestamp", label: "Time", render: (r) => new Date(r.timestamp).toLocaleString() },
  { key: "device_id", label: "Device" },
  { key: "src_ip", label: "Source" },
  { key: "dst_ip", label: "Destination" },
  { key: "app", label: "Application" },
  { key: "action", label: "Action" },
  { key: "matched_rule", label: "Rule Name", render: (r) => r.matched_rule || "—" },
  { key: "bytes_total", label: "Bytes", render: (r) => r.bytes_total ?? "—" },
];

// Real, searchable Traffic Log tab -- source IP / destination IP /
// device, with "All Devices" searching across every onboarded
// firewall when nothing is selected. Hits the same real /logs API
// as every other tab, just with filters attached.
function TrafficLogsTab() {
  const [devices, setDevices] = useState([]);
  const [filters, setFilters] = useState({ src_ip: "", dst_ip: "", device_id: "", since_minutes: "60" });
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [searched, setSearched] = useState(false);

  useEffect(() => { api.listDevices().then(setDevices).catch(() => {}); }, []);

  const search = async () => {
    try {
      setRows(await api.searchLogs({
        event_type: "traffic",
        ...(filters.src_ip && { src_ip: filters.src_ip }),
        ...(filters.dst_ip && { dst_ip: filters.dst_ip }),
        ...(filters.device_id && { device_id: filters.device_id }),
        since_minutes: filters.since_minutes || "60",
      }));
      setSearched(true);
    } catch (err) { setError(err.message); }
  };

  return (
    <div>
      <FilterBar
        fields={[
          { key: "src_ip", label: "Source IP", placeholder: "10.1.1.5" },
          { key: "dst_ip", label: "Destination IP", placeholder: "157.240.1.1" },
          {
            key: "device_id", label: "Device", type: "select",
            options: [
              { value: "", label: "All Devices" },
              ...devices.map((d) => ({ value: d.device_id, label: d.hostname })),
            ],
          },
          { key: "since_minutes", label: "Since (minutes)", placeholder: "60" },
        ]}
        value={filters}
        onChange={(k, v) => setFilters({ ...filters, [k]: v })}
        onSubmit={search}
        extra={<button type="button" className="btn-ghost"><Download size={14} /> Export</button>}
      />
      {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{error}</div>}
      <DataTable
        enableColumnPicker
        columns={TRAFFIC_COLUMNS}
        rows={rows}
        emptyLabel={searched ? "No matching traffic logs. Try Search with broader filters." : "Set filters and click Search — leave Device on All Devices to search every onboarded firewall."}
      />
    </div>
  );
}

// Threat / URL / System: no search fields, just the real logs
// collected for that type in the last hour. Devices unreachable or
// not yet polled just show up as an empty table -- never mocked.
function ReadOnlyLogTab({ eventType, columns, emptyLabel }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api.searchLogs({ event_type: eventType, since_minutes: "60" })
      .then((data) => { if (!cancelled) setRows(data); })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [eventType]);

  if (loading) return <div className="empty-state" style={{ padding: "32px 0" }}><p>Loading logs…</p></div>;
  if (error) return <div className="empty-state" style={{ padding: "32px 0" }}><p style={{ color: "var(--bad)" }}>{error}</p></div>;
  return <DataTable enableColumnPicker columns={columns} rows={rows} emptyLabel={emptyLabel} />;
}

// Real, live session/flow lookup -- firewall session tables (PAN-OS/
// FortiOS) or router NetFlow cache (Cisco IOS), queried directly from
// the device on demand. This is what lets you confirm a flow actually
// transited a specific hop, independent of running a full diagnostics
// trace.
function SessionsTab() {
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState("");
  const [filters, setFilters] = useState({ src_ip: "", dst_ip: "" });
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [searched, setSearched] = useState(false);

  useEffect(() => { api.listDevices().then(setDevices).catch(() => {}); }, []);

  const search = async () => {
    if (!deviceId) { setError("Select a device first."); return; }
    setError(null);
    try {
      setRows(await api.getSessions(deviceId, {
        ...(filters.src_ip && { src_ip: filters.src_ip }),
        ...(filters.dst_ip && { dst_ip: filters.dst_ip }),
      }));
      setSearched(true);
    } catch (err) { setError(err.message); }
  };

  return (
    <div>
      <div className="filter-bar-fields" style={{ marginBottom: 10 }}>
        <div className="filter-field">
          <label>Device</label>
          <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
            <option value="">Select…</option>
            {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.hostname} ({d.vendor})</option>)}
          </select>
        </div>
        <div className="filter-field">
          <label>Source IP</label>
          <input value={filters.src_ip} onChange={(e) => setFilters({ ...filters, src_ip: e.target.value })} placeholder="10.1.1.5" />
        </div>
        <div className="filter-field">
          <label>Destination IP</label>
          <input value={filters.dst_ip} onChange={(e) => setFilters({ ...filters, dst_ip: e.target.value })} placeholder="157.240.1.1" />
        </div>
      </div>
      <button className="btn-primary" onClick={search} style={{ marginBottom: 14 }}>Search live sessions</button>
      {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{error}</div>}
      <DataTable
        columns={[
          { key: "src_ip", label: "Source" },
          { key: "src_port", label: "Src Port" },
          { key: "dst_ip", label: "Destination" },
          { key: "dst_port", label: "Dst Port" },
          { key: "protocol", label: "Protocol" },
          { key: "app", label: "Application", render: (r) => r.app || "—" },
          { key: "state", label: "State" },
        ]}
        rows={rows}
        emptyLabel={searched ? "No matching sessions/flows found on this device right now." : "Select a device and click Search — this queries the device live, not a log archive."}
      />
    </div>
  );
}

export default function Logs() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeTab = location.pathname.split("/")[2] || "traffic";

  return (
    <div>
      <div className="page-head">
        <div><h1>Logs</h1><p>Live logs collected from every onboarded device, kept for 30 minutes.</p></div>
      </div>
      <div className="tab-row">
        {TABS.map((t) => (
          <button key={t.key} className={`tab-btn ${activeTab === t.key ? "tab-active" : ""}`} onClick={() => navigate(`/logs/${t.key}`)}>
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "traffic" && <Card><TrafficLogsTab /></Card>}
      {activeTab === "threat" && (
        <Card>
          <ReadOnlyLogTab
            eventType="threat"
            emptyLabel="No logs found."
            columns={[
              { key: "timestamp", label: "Time", render: (r) => new Date(r.timestamp).toLocaleString() },
              { key: "device_id", label: "Device" },
              { key: "src_ip", label: "Source" },
              { key: "dst_ip", label: "Destination" },
              { key: "app", label: "Application" },
              { key: "threat_name", label: "Threat" },
              { key: "severity", label: "Severity" },
            ]}
          />
        </Card>
      )}
      {activeTab === "url" && (
        <Card>
          <ReadOnlyLogTab
            eventType="url"
            emptyLabel="No logs found."
            columns={[
              { key: "timestamp", label: "Time", render: (r) => new Date(r.timestamp).toLocaleString() },
              { key: "device_id", label: "Device" },
              { key: "user", label: "User" },
              { key: "url", label: "URL" },
              { key: "category", label: "Category" },
              { key: "action", label: "Action" },
            ]}
          />
        </Card>
      )}
      {activeTab === "system" && (
        <Card>
          <ReadOnlyLogTab
            eventType="system"
            emptyLabel="No logs found."
            columns={[
              { key: "timestamp", label: "Time", render: (r) => new Date(r.timestamp).toLocaleString() },
              { key: "device_id", label: "Device" },
              { key: "severity", label: "Severity" },
              { key: "raw_original", label: "Message" },
            ]}
          />
        </Card>
      )}
      {activeTab === "sessions" && <Card><SessionsTab /></Card>}
    </div>
  );
}
