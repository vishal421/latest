// Talks to the existing InfraOS backend exactly as-is -- no API
// contract changes. Pages that have a real backend feature use this;
// pages without one yet (Traffic Analytics widgets, Alarms, License,
// Compliance, Reports, Settings, Support) use mockData.js
// instead, clearly labeled in the UI as such.
//
// API_BASE resolution order:
//   1. window.INFRAOS_API_BASE -- runtime override, e.g. injected via a
//      small <script> tag at deploy time if frontend and backend ever
//      need to live on different origins/domains.
//   2. VITE_API_URL -- build-time override (frontend/.env.production etc).
//   3. "" (relative) -- the default and recommended setup. Requests go
//      to the SAME origin the page was served from (e.g.
//      http://34.228.196.171:3110/devices), and whatever's serving the
//      frontend (nginx in prod, the Vite dev server locally) reverse-
//      proxies API paths to the backend. This is what makes the exact
//      same build work unmodified on localhost, a staging box, or behind
//      a real domain -- nothing here ever needs to know the backend's
//      host or port.
const API_BASE =
  (typeof window !== "undefined" && window.INFRAOS_API_BASE) ||
  import.meta.env.VITE_API_URL ||
  "";

async function request(path, opts) {
  const res = await fetch(API_BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok && res.status !== 207) throw new Error(body.detail || res.statusText);
  return body;
}

// When API_BASE is relative (the default), derive the websocket origin
// from the page's own location instead of trying to rewrite an empty
// string -- ws(s)://<same host the page was loaded from>.
function resolveWsBase(base) {
  if (base) return base.replace(/^http/, "ws");
  if (typeof window === "undefined") return "";
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}`;
}

export const api = {
  base: API_BASE,
  wsBase: resolveWsBase(API_BASE),

  // Live topology status (Phase 1 real-time monitoring): pushes
  // {devices, interfaces} snapshots so the Network Diagram canvas can
  // recolor links / update alarm badges without polling from the
  // client. Returns the raw WebSocket so the caller controls its
  // lifecycle (close on unmount, etc).
  openTopologyStatusStream: (onSnapshot, onError) => {
    const ws = new WebSocket(`${resolveWsBase(API_BASE)}/network-diagram/ws/status`);
    ws.onmessage = (evt) => {
      try { onSnapshot(JSON.parse(evt.data)); } catch { /* ignore malformed frame */ }
    };
    if (onError) ws.onerror = onError;
    return ws;
  },
  getTopologyStatus: () => request("/network-diagram/status"),

  listDevices: () => request("/devices"),
  addDevice: (payload) => request("/devices", { method: "POST", body: JSON.stringify(payload) }),
  deleteDevice: (id) => request(`/devices/${id}`, { method: "DELETE" }),

  getHealthHistory: (deviceId) => request(`/health/${deviceId}`),
  pollHealthNow: (deviceId) => request(`/health/${deviceId}/poll-now`, { method: "POST" }),

  searchLogs: (params) => request(`/logs?${new URLSearchParams(params).toString()}`),

  runDiagnostics: (payload) => request("/diagnostics", { method: "POST", body: JSON.stringify(payload) }),
  runTroubleshooting: (payload) => request("/troubleshooting", { method: "POST", body: JSON.stringify(payload) }),

  getNetworkDiagram: () => request("/network-diagram"),
  getDiagramNodeTypes: () => request("/network-diagram/node-types"),
  createDiagramNode: (payload) => request("/network-diagram/nodes", { method: "POST", body: JSON.stringify(payload) }),
  updateDiagramNode: (id, payload) => request(`/network-diagram/nodes/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteDiagramNode: (id) => request(`/network-diagram/nodes/${id}`, { method: "DELETE" }),
  createDiagramEdge: (payload) => request("/network-diagram/edges", { method: "POST", body: JSON.stringify(payload) }),
  deleteDiagramEdge: (id) => request(`/network-diagram/edges/${id}`, { method: "DELETE" }),
  getDeviceInterfaces: (deviceId) => request(`/topology/interfaces/${deviceId}`),

  getTopologyGraph: () => request("/topology/graph"),
  getTopologyDrift: () => request("/topology/drift"),
  runTopologyDiscovery: () => request("/topology/discover", { method: "POST" }),
  listDeviceInterfaces: (deviceId) => request(`/topology/interfaces/${deviceId}`),
  getInterfaceHistory: (deviceId, params = {}) => request(`/topology/interfaces/${deviceId}/history?${new URLSearchParams(params).toString()}`),
  addTopologyLink: (payload) => request("/topology/links", { method: "POST", body: JSON.stringify(payload) }),

  getCliQuickCommands: (deviceId) => request(`/cli/quick-commands/${deviceId}`),
  searchAudit: (params) => request(`/cli/audit?${new URLSearchParams(params).toString()}`),

  listAlarms: (params = {}) => request(`/alarms?${new URLSearchParams(params).toString()}`),
  getAlarmsSummary: () => request("/alarms/summary"),

  listLicenses: (params = {}) => request(`/licenses?${new URLSearchParams(params).toString()}`),
  pollLicensesNow: (deviceId) => request(`/licenses/${deviceId}/poll-now`, { method: "POST" }),

  getSessions: (deviceId, params = {}) => request(`/sessions/${deviceId}?${new URLSearchParams(params).toString()}`),

  getTrafficAnalytics: (params = {}) => request(`/traffic-analytics?${new URLSearchParams(params).toString()}`),

  listConfigBackups: (params = {}) => request(`/config-backups?${new URLSearchParams(params).toString()}`),
  getConfigBackupContent: (backupId) => request(`/config-backups/${backupId}/content`),
  pollConfigBackupNow: (deviceId) => request(`/config-backups/${deviceId}/poll-now`, { method: "POST" }),

  getReportSummary: (params = {}) => request(`/reports/summary?${new URLSearchParams(params).toString()}`),

  getProfile: () => request("/settings/profile"),
  updateProfile: (payload) => request("/settings/profile", { method: "PUT", body: JSON.stringify(payload) }),
  getLicenseSummary: () => request("/settings/license-summary"),

  addIdentity: (payload) => request("/identities", { method: "POST", body: JSON.stringify(payload) }),
  resolveIdentity: (ip) => request(`/identities/resolve?ip_address=${encodeURIComponent(ip)}`),
};
