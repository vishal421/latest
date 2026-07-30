import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import Card from "../../components/Card";
import { api } from "../../api";

export default function LicenseStatus() {
  const [devices, setDevices] = useState([]);
  const [licenses, setLicenses] = useState([]);
  const [error, setError] = useState(null);
  const [selectedDevice, setSelectedDevice] = useState("all");
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState(null);

  const load = () => {
    Promise.all([api.listDevices(), api.listLicenses()])
      .then(([d, l]) => { setDevices(d); setLicenses(l); })
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  // Licenses are polled automatically every 6 hours (see
  // LICENSE_POLL_INTERVAL_SECONDS in the scheduler) -- this triggers
  // that same real poll-now on demand, either for one device or,
  // when "All Devices" is selected, for every onboarded device in turn.
  const fetchNow = async () => {
    setFetching(true);
    setFetchError(null);
    const targets = selectedDevice === "all" ? devices.map((d) => d.device_id) : [selectedDevice];
    const failures = [];
    for (const deviceId of targets) {
      try {
        const updated = await api.pollLicensesNow(deviceId);
        setLicenses((prev) => [...prev.filter((l) => l.device_id !== deviceId), ...updated]);
      } catch (err) {
        const device = devices.find((d) => d.device_id === deviceId);
        failures.push(`${device?.hostname || deviceId}: ${err.message}`);
      }
    }
    if (failures.length > 0) setFetchError(failures.join(" · "));
    setFetching(false);
  };

  const licensesByDevice = (deviceId) => licenses.filter((l) => l.device_id === deviceId);
  const visibleDevices = selectedDevice === "all" ? devices : devices.filter((d) => d.device_id === selectedDevice);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>License Status</h1>
          <p>Real license/entitlement data pulled from each device — polled automatically every 6 hours, or fetch now below.</p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
          <div>
            <label>Device</label>
            <select value={selectedDevice} onChange={(e) => setSelectedDevice(e.target.value)}>
              <option value="all">All Devices</option>
              {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.hostname}</option>)}
            </select>
          </div>
          <button className="btn-primary" disabled={fetching || devices.length === 0} onClick={fetchNow}>
            <RefreshCw size={14} className={fetching ? "spin" : ""} />
            {fetching ? "Fetching…" : "Fetch Now"}
          </button>
        </div>
      </div>
      {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{error}</div>}
      {fetchError && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{fetchError}</div>}
      {devices.length === 0 && !error && (
        <div className="ui-card">
          <div className="empty-state" style={{ padding: "50px 20px" }}>
            <h3>No devices onboarded</h3>
            <p>Onboard a Palo Alto, Fortigate, or Cisco IOS device to see its real license status here.</p>
          </div>
        </div>
      )}

      {visibleDevices.map((d) => {
        const deviceLicenses = licensesByDevice(d.device_id);
        return (
          <Card key={d.device_id} title={`${d.hostname} (${d.mgmt_ip})`}>
            {deviceLicenses.length === 0 ? (
              <div className="empty-state" style={{ padding: "20px 0" }}>
                <p>No license data yet for this device. Click Fetch Now, or wait for the next scheduled poll.</p>
              </div>
            ) : (
              <div className="card-grid">
                {deviceLicenses.map((l, i) => (
                  <Card key={i} className={l.status === "expired" ? "stat-card stat-bad" : "stat-card"}>
                    <div className="stat-label">{l.feature}</div>
                    <div className="stat-value" style={{ textTransform: "capitalize" }}>{l.status}</div>
                    <div className="stat-sub">
                      {l.expiry_date ? `Expires ${new Date(l.expiry_date).toLocaleDateString()}` : "No expiry"}
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
