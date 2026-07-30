import { useEffect, useRef, useState } from "react";
import Card from "../../components/Card";
import { api } from "../../api";

const SAVED_COMMANDS = [
  "show version", "show ip interface brief", "show running-config",
  "show ip route", "show mac address-table", "show interfaces",
];

const CONFIG_KEYWORDS = ["configure", "conf t", "set ", "delete ", "commit", "edit ", "no ", "write memory", "copy running-config", "clear "];
function looksLikeConfigCommand(cmd) {
  const lowered = cmd.trim().toLowerCase();
  return CONFIG_KEYWORDS.some((kw) => lowered.startsWith(kw));
}

export default function Cli() {
  const [devices, setDevices] = useState([]);
  const [selected, setSelected] = useState("");
  const [connected, setConnected] = useState(false);
  const [lines, setLines] = useState([]);
  const [command, setCommand] = useState("");
  const [quickCommands, setQuickCommands] = useState({});
  const wsRef = useRef(null);
  const termRef = useRef(null);

  useEffect(() => { api.listDevices().then(setDevices).catch(() => {}); }, []);
  useEffect(() => { if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight; }, [lines]);

  const connect = () => {
    if (!selected) return;
    api.getCliQuickCommands(selected).then(setQuickCommands).catch(() => setQuickCommands({}));
    const ws = new WebSocket(`${api.wsBase}/cli/ws/${selected}?admin_user=vish&role=config_admin`);
    ws.onopen = () => setConnected(true);
    ws.onclose = (evt) => {
      setConnected(false);
      // A clean, expected close (the Disconnect button) is code 1000.
      // Anything else means the session dropped unexpectedly -- say so,
      // since the backend's own error message (if any) may have arrived
      // in a separate onmessage just before this fires.
      if (evt.code !== 1000) {
        setLines((prev) => [...prev, `-- connection closed (code ${evt.code}) --`]);
      }
    };
    ws.onerror = () => setLines((prev) => [...prev, "-- connection error --"]);
    ws.onmessage = (evt) => setLines((prev) => [...prev, evt.data]);
    wsRef.current = ws;
  };
  const disconnect = () => { wsRef.current && wsRef.current.close(1000); };

  const sendRaw = (cmd) => {
    if (!wsRef.current) return;
    const tag = looksLikeConfigCommand(cmd) ? "[CONFIG] " : "";
    setLines((prev) => [...prev, `$ ${tag}${cmd}`]);
    wsRef.current.send(cmd);
  };

  const send = (e) => {
    e.preventDefault();
    if (!command.trim() || !wsRef.current) return;
    if (looksLikeConfigCommand(command) && !window.confirm(`Send configuration command?\n\n"${command}"\n\nThis will be recorded in the audit log.`)) return;
    sendRaw(command);
    setCommand("");
  };

  return (
    <div>
      <div className="page-head">
        <div><h1>CLI</h1><p>Full, audited terminal access to any onboarded device.</p></div>
      </div>

      <Card>
        <div className="grid-2col" style={{ marginBottom: 16 }}>
          <div>
            <label>Device</label>
            <select value={selected} onChange={(e) => setSelected(e.target.value)} disabled={connected}>
              <option value="">Select a device…</option>
              {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.hostname} ({d.vendor})</option>)}
            </select>
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            {!connected
              ? <button className="btn-primary" onClick={connect} disabled={!selected}>Connect</button>
              : <button className="btn-primary" onClick={disconnect} style={{ background: "var(--bad)", color: "#fff" }}>Disconnect</button>}
          </div>
        </div>

        <div className="cli-layout">
          <div className="cli-panel">
            <div className="cli-panel-head">Saved Commands</div>
            {SAVED_COMMANDS.map((c) => (
              <div key={c} className="cli-saved-cmd" onClick={() => connected && sendRaw(c)}>{c}</div>
            ))}
            {(quickCommands.enter_config_mode || quickCommands.save_config) && (
              <>
                <div className="cli-panel-head" style={{ borderTop: "1px solid var(--border)" }}>Vendor Quick Actions</div>
                {quickCommands.enter_config_mode && (
                  <div className="cli-saved-cmd" onClick={() => connected && window.confirm(`Run "${quickCommands.enter_config_mode}"?`) && sendRaw(quickCommands.enter_config_mode)}>
                    {quickCommands.enter_config_mode}
                  </div>
                )}
                {quickCommands.save_config && (
                  <div className="cli-saved-cmd" onClick={() => connected && window.confirm(`Run "${quickCommands.save_config}"?`) && sendRaw(quickCommands.save_config)}>
                    {quickCommands.save_config}
                  </div>
                )}
              </>
            )}
          </div>

          <div className="cli-panel">
            <div className="cli-panel-head">Terminal {connected && <span style={{ color: "var(--good)" }}>· connected</span>}</div>
            <div className="cli-terminal" ref={termRef}>
              {lines.length === 0 ? "// connect to a device to begin" : lines.join("\n")}
            </div>
            <form className="cli-input-row" onSubmit={send}>
              <input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="type a command…" disabled={!connected} />
              <button className="btn-primary" type="submit" disabled={!connected}>Run</button>
            </form>
          </div>

          <div className="cli-panel">
            <div className="cli-panel-head">AI Assistant</div>
            <div className="cli-output-panel">
              Command explanations and suggested next steps will appear here once the assistant is wired in.
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
