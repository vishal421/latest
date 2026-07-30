import { useEffect, useState } from "react";
import BarWidget from "../../components/BarWidget";
import { api } from "../../api";

export default function TopTraffic() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getTrafficAnalytics({ since_minutes: "60" }).then(setData).catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <div className="page-head">
        <div><h1>Top Traffic</h1><p>Highest-volume source and destination addresses, from real logged traffic.</p></div>
      </div>
      {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{error}</div>}
      {data && (
        <div className="grid-2col">
          <BarWidget title="Top Source IPs" data={(data.top_source_ips || []).map((e) => ({ ip: e.key, bytes: e.bytes_total }))} xKey="ip" yKey="bytes" height={280} />
          <BarWidget title="Top Destination IPs" data={(data.top_destination_ips || []).map((e) => ({ ip: e.key, bytes: e.bytes_total }))} xKey="ip" yKey="bytes" height={280} />
        </div>
      )}
    </div>
  );
}
