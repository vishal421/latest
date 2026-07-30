import { useEffect, useState } from "react";
import Card from "../../components/Card";
import DataTable from "../../components/DataTable";
import { api } from "../../api";

export default function DeniedTraffic() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getTrafficAnalytics({ since_minutes: "60" })
      .then((d) => setRows(d.denied))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <div className="page-head">
        <div><h1>Denied Traffic</h1><p>Destinations most frequently blocked across onboarded firewalls, from real traffic logs.</p></div>
      </div>
      {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{error}</div>}
      <Card>
        <DataTable
          columns={[
            { key: "dst_ip", label: "Destination" },
            { key: "matched_rule", label: "Matched Rule" },
            { key: "hits", label: "Hits" },
          ]}
          rows={rows}
          emptyLabel="No denied traffic logged yet."
        />
      </Card>
    </div>
  );
}
