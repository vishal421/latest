import {
  LayoutDashboard, Activity, FileText, Wrench, Settings2,
  ShieldCheck, BarChart3, Sliders, LifeBuoy,
} from "lucide-react";

// Data-driven nav so adding a new module later is one entry here,
// not a Sidebar code change -- per the brief's "reusable, many new
// modules will be added later."
export const NAV = [
  {
    key: "dashboard", label: "Dashboard", icon: LayoutDashboard,
    children: [
      { key: "overview", label: "Overview", path: "/dashboard" },
      { key: "health", label: "Health Status", path: "/dashboard/health" },
      { key: "topology", label: "Network Topology", path: "/dashboard/topology" },
      { key: "network-diagram", label: "Network Diagram", path: "/dashboard/network-diagram" },
      { key: "license", label: "License Status", path: "/dashboard/license" },
    ],
  },
  {
    key: "traffic", label: "Traffic Analytics", icon: Activity,
    children: [
      { key: "top-traffic", label: "Top Traffic", path: "/traffic/top" },
      { key: "applications", label: "Applications", path: "/traffic/applications" },
      { key: "link-utilization", label: "Link Utilization", path: "/traffic/link-utilization" },
      { key: "denied-traffic", label: "Denied Traffic", path: "/traffic/denied" },
    ],
  },
  { key: "logs", label: "Logs", icon: FileText, path: "/logs" },
  { key: "troubleshooting", label: "Troubleshooting", icon: Wrench, path: "/troubleshooting" },
  {
    key: "configuration", label: "Configuration", icon: Settings2,
    children: [
      { key: "devices", label: "Devices", path: "/configuration/devices" },
      { key: "templates", label: "Templates", path: "/configuration/templates" },
      { key: "cli", label: "CLI", path: "/configuration/cli" },
      { key: "backup", label: "Configuration Backup", path: "/configuration/backup" },
    ],
  },
  { key: "compliance", label: "Compliance", icon: ShieldCheck, path: "/compliance" },
  { key: "reports", label: "Reports", icon: BarChart3, path: "/reports" },
  { key: "settings", label: "Settings", icon: Sliders, path: "/settings" },
  { key: "support", label: "Support", icon: LifeBuoy, path: "/support" },
];
