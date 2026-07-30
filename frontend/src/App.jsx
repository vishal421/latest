import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ShieldCheck, LifeBuoy, FileStack } from "lucide-react";
import Layout from "./components/Layout";

import Overview from "./pages/dashboard/Overview";
import HealthStatus from "./pages/dashboard/HealthStatus";
import NetworkTopology from "./pages/dashboard/NetworkTopology";
import NetworkDiagram from "./pages/NetworkDiagram";
import LicenseStatus from "./pages/dashboard/LicenseStatus";

import TrafficAnalytics from "./pages/TrafficAnalytics";
import TopTraffic from "./pages/traffic/TopTraffic";
import Applications from "./pages/traffic/Applications";
import LinkUtilization from "./pages/traffic/LinkUtilization";
import DeniedTraffic from "./pages/traffic/DeniedTraffic";

import Logs from "./pages/Logs";
import Troubleshooting from "./pages/Troubleshooting";

import Devices from "./pages/configuration/Devices";
import Cli from "./pages/configuration/Cli";
import Backup from "./pages/configuration/Backup";

import Reports from "./pages/Reports";
import Settings from "./pages/Settings";

import Placeholder from "./pages/Placeholder";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          <Route path="/dashboard" element={<Overview />} />
          <Route path="/dashboard/health" element={<HealthStatus />} />
          <Route path="/dashboard/topology" element={<NetworkTopology />} />
          <Route path="/dashboard/network-diagram" element={<NetworkDiagram />} />
          <Route path="/dashboard/license" element={<LicenseStatus />} />

          <Route path="/traffic" element={<TrafficAnalytics />} />
          <Route path="/traffic/top" element={<TopTraffic />} />
          <Route path="/traffic/applications" element={<Applications />} />
          <Route path="/traffic/link-utilization" element={<LinkUtilization />} />
          <Route path="/traffic/denied" element={<DeniedTraffic />} />

          <Route path="/logs" element={<Navigate to="/logs/traffic" replace />} />
          <Route path="/logs/:tab" element={<Logs />} />

          <Route path="/troubleshooting" element={<Troubleshooting />} />

          <Route path="/configuration" element={<Navigate to="/configuration/devices" replace />} />
          <Route path="/configuration/devices" element={<Devices />} />
          <Route path="/configuration/templates" element={<Placeholder icon={FileStack} title="Templates" description="Reusable configuration templates across vendors." />} />
          <Route path="/configuration/cli" element={<Cli />} />
          <Route path="/configuration/backup" element={<Backup />} />

          <Route path="/compliance" element={<Placeholder icon={ShieldCheck} title="Compliance" description="Policy and configuration compliance scoring across every onboarded device." />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/support" element={<Placeholder icon={LifeBuoy} title="Support" description="Documentation, ticketing, and contact options." />} />

          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
