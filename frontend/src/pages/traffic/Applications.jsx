import { useEffect, useState } from "react";
import BarWidget from "../../components/BarWidget";
import { api } from "../../api";

export default function Applications() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getTrafficAnalytics({ since_minutes: "60" }).then(setData).catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <div className="page-head">
        <div><h1>Applications</h1><p>Bandwidth consumption by application, from real logged traffic.</p></div>
      </div>
      {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{error}</div>}
      {data && (
        <BarWidget
          title="Top Applications"
          data={(data.top_applications || []).map((e) => ({ app: e.key, bytes: e.bytes_total }))}
          xKey="app" yKey="bytes" height={320}
        />
      )}
    </div>
  );
}
