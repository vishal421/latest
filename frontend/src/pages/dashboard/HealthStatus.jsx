import Card from "../../components/Card";
import DeviceHealthTable from "../../components/DeviceHealthTable";

export default function HealthStatus() {
  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Health Status</h1>
          <p>Live CPU, memory, and uptime across every onboarded device.</p>
        </div>
      </div>
      <Card>
        <DeviceHealthTable />
      </Card>
    </div>
  );
}
