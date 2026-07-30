import { useEffect, useState, useCallback } from "react";
import Card from "../../components/Card";
import TopologyView from "../../components/TopologyView";
import { api } from "../../api";

export default function NetworkTopology() {
  const [graph, setGraph] = useState({ nodes: [], links: [] });
  const [drift, setDrift] = useState([]);
  const [discovering, setDiscovering] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setGraph(await api.getTopologyGraph());
      setDrift(await api.getTopologyDrift());
    } catch (err) { setError(err.message); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const discover = async () => {
    setDiscovering(true);
    try { await api.runTopologyDiscovery(); await load(); }
    catch (err) { setError(err.message); }
    finally { setDiscovering(false); }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Network Topology</h1>
          <p>Auto-layered from wired links; refreshes every 5 seconds.</p>
        </div>
        <button className="btn-primary" onClick={discover} disabled={discovering}>
          {discovering ? "Discovering…" : "Run discovery"}
        </button>
      </div>
      {error && <div style={{ color: "var(--bad)", marginBottom: 12, fontSize: 13 }}>{error}</div>}
      <Card>
        <TopologyView nodes={graph.nodes} links={graph.links} />
      </Card>

      {drift.length > 0 && (
        <>
          <div style={{ height: 20 }} />
          <Card title="Topology drift">
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 10 }}>
              Differences between the manually-drawn topology and what discovery actually found.
            </div>
            {drift.map((d, i) => (
              <div key={i} style={{ fontSize: 12.5, fontFamily: "var(--font-mono)", padding: "6px 0", borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
                {d.device_a} ↔ {d.device_b} — {d.drift_type.replaceAll("_", " ")}
              </div>
            ))}
          </Card>
        </>
      )}
    </div>
  );
}
