import { ArrowRight, Check, X as XIcon, HelpCircle } from "lucide-react";

// The signature element of the platform: a horizontal correlation
// chain (Host -> Switch -> Core -> Firewall -> Router -> Internet ->
// Destination). Deliberately plain -- a thin connecting line and small
// status dots, no glow or gradient, in keeping with the enterprise
// brief. Each hop is a card carrying the fields the Correlation page
// spec calls for: status, latency, matched policy/route/NAT, reason.
export default function Timeline({ hops }) {
  if (!hops || hops.length === 0) {
    return <div className="timeline-empty">No trace has been run yet.</div>;
  }
  return (
    <div className="timeline">
      {hops.map((hop, i) => (
        <div className="timeline-item" key={i}>
          <div className="timeline-node">
            <div className={`timeline-dot dot-${hop.status}`}>
              {hop.status === "allow" && <Check size={12} />}
              {hop.status === "deny" && <XIcon size={12} />}
              {hop.status === "unknown" && <HelpCircle size={12} />}
            </div>
            {i < hops.length - 1 && <div className="timeline-line" />}
          </div>
          <div className="timeline-card">
            <div className="timeline-card-head">
              <span className="timeline-hop-label">{hop.label}</span>
              <span className={`status-badge status-${hop.status === "allow" ? "good" : hop.status === "deny" ? "bad" : "warn"}`}>
                {hop.status === "allow" ? "Allow" : hop.status === "deny" ? "Deny" : "Unknown"}
              </span>
            </div>
            <div className="timeline-card-meta">
              {hop.latencyMs != null && <span>Latency: {hop.latencyMs}ms</span>}
              {hop.matchedPolicy && <span>Policy: {hop.matchedPolicy}</span>}
              {hop.matchedRoute && <span>Route: {hop.matchedRoute}</span>}
              {hop.matchedNat && <span>NAT: {hop.matchedNat}</span>}
            </div>
            {hop.reason && <div className="timeline-card-reason">{hop.reason}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}
