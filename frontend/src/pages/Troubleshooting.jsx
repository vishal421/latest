import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, MinusCircle } from "lucide-react";
import Card from "../components/Card";
import { api } from "../api";

const STAGE_LABELS = {
  router_log: "Router Log",
  firewall_traffic: "Firewall Traffic",
  nat: "NAT",
  routing: "Routing",
  return_traffic: "Return Traffic",
};

const SOURCE_LABELS = {
  traffic_log: "Traffic Log",
  session_log: "Session Log",
  config_file: "Config File",
  "n/a": "—",
};

function StatusIcon({ status }) {
  if (status === "pass") return <CheckCircle2 size={16} color="var(--good)" />;
  if (status === "fail") return <XCircle size={16} color="var(--bad)" />;
  return <MinusCircle size={16} color="var(--text-muted)" />;
}

function StepRow({ step, deviceName }) {
  return (
    <div style={{
      display: "flex", gap: 14, alignItems: "flex-start",
      padding: "12px 14px", borderRadius: 8, background: "var(--surface-2)",
      border: "1px solid var(--border)", marginBottom: 8,
    }}>
      <div style={{ marginTop: 2 }}><StatusIcon status={step.status} /></div>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontSize: 12.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.03em", color: "var(--text-muted)" }}>
            {STAGE_LABELS[step.stage] || step.stage}{deviceName ? ` — ${deviceName}` : ""}
          </span>
          <span style={{ fontSize: 11, color: "var(--text-faint)" }}>source: {SOURCE_LABELS[step.source] || step.source}</span>
        </div>
        <div style={{ fontSize: 13.5, marginTop: 4 }}>{step.summary}</div>
      </div>
    </div>
  );
}

export default function Troubleshooting() {
  const [devices, setDevices] = useState([]);
  const [srcIp, setSrcIp] = useState("");
  const [dstIp, setDstIp] = useState("");
  const [protocol, setProtocol] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.listDevices().then(setDevices).catch(() => {}); }, []);

  const deviceName = (id) => devices.find((d) => d.device_id === id)?.hostname || id;

  const run = async () => {
    if (!srcIp || !dstIp) { setError("Source and Destination are required."); return; }
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await api.runTroubleshooting({
        src_ip: srcIp, dst_ip: dstIp,
        ...(protocol && { protocol }),
        ...(deviceId && { device_id: deviceId }),
      });
      setResult(r);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Troubleshooting</h1>
          <p>Traces a flow across stored traffic logs, live session tables, and each device's downloaded configuration — never simulated.</p>
        </div>
      </div>

      <Card>
        <div className="filter-bar-fields">
          <div className="filter-field">
            <label>Source IP <span style={{ color: "var(--bad)" }}>*</span></label>
            <input value={srcIp} onChange={(e) => setSrcIp(e.target.value)} placeholder="10.1.1.5" />
          </div>
          <div className="filter-field">
            <label>Destination IP <span style={{ color: "var(--bad)" }}>*</span></label>
            <input value={dstIp} onChange={(e) => setDstIp(e.target.value)} placeholder="157.240.1.1" />
          </div>
          <div className="filter-field">
            <label>Protocol</label>
            <select value={protocol} onChange={(e) => setProtocol(e.target.value)}>
              <option value="">Any</option>
              <option value="tcp">TCP</option>
              <option value="udp">UDP</option>
              <option value="icmp">ICMP</option>
            </select>
          </div>
          <div className="filter-field">
            <label>Device</label>
            <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
              <option value="">Every onboarded device</option>
              {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.hostname}</option>)}
            </select>
          </div>
        </div>
        <button className="btn-primary" onClick={run} disabled={loading} style={{ marginTop: 12 }}>
          {loading ? "Running…" : "Run Troubleshooting"}
        </button>
      </Card>
      {error && <div style={{ color: "var(--bad)", fontSize: 13, margin: "12px 0" }}>{error}</div>}

      {result && (
        <>
          <div style={{ height: 20 }} />
          <Card title="Trace">
            {result.steps.length === 0
              ? <div className="empty-state" style={{ padding: "20px 0" }}><p>No devices matched this trace.</p></div>
              : result.steps.map((step, i) => <StepRow key={i} step={step} deviceName={step.device_id ? deviceName(step.device_id) : null} />)
            }
          </Card>

          <div style={{ height: 20 }} />
          <Card title="Verdict">
            <div style={{ fontSize: 13.5 }}>{result.verdict}</div>
          </Card>
        </>
      )}
    </div>
  );
}
