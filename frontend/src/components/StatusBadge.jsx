// Maps a status/severity word to one of the three brand status colors.
// Deliberately a small, closed vocabulary -- consistent meaning across
// every table in the app (device health, alarms, logs, backups).
const TONE_MAP = {
  // good
  healthy: "good", up: "good", allow: "good", allowed: "good", success: "good",
  active: "good", resolved: "good", low: "good",
  // warn
  warning: "warn", medium: "warn", degraded: "warn", pending: "warn",
  // bad
  critical: "bad", down: "bad", deny: "bad", denied: "bad", blocked: "bad",
  failed: "bad", high: "bad",
};

export default function StatusBadge({ status }) {
  const key = String(status || "").toLowerCase();
  const tone = TONE_MAP[key] || "warn";
  return <span className={`status-badge status-${tone}`}>{status}</span>;
}
