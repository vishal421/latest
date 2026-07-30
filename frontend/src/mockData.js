// Mock data for sections that don't have a backend yet: alarms,
// license status, traffic analytics widgets, and the placeholder
// modules (Automation, Compliance, Reports, Settings, Support).
// Every page using this data shows a small "mock data" indicator so
// it's never confused with the real, wired-up features (Devices,
// Health, Logs, Diagnostics/Correlation, Topology, CLI, Audit).

// Alarms are now real -- see api.listAlarms() / api.getAlarmsSummary(),
// backed by app/alerting.py's threshold engine. mockAlarms removed.

// License Status is now real -- see api.listLicenses(), backed by
// each firewall's real license API. mockLicenses removed.

// Traffic Analytics (top talkers, applications, bandwidth, denied
// traffic) is now real -- see api.getTrafficAnalytics(), backed by
// real aggregation over logged traffic. mockTrafficTrend/
// mockTopSourceIps/mockTopDestinations/mockTopApplications/
// mockDeniedDestinations removed.

// Threat/URL/System logs are now real -- see api.searchLogs({ event_type })
// backed by each vendor's real log API. mockThreatLogs/mockUrlLogs/
// mockSystemLogs removed.

// Configuration Backup is now real -- see api.listConfigBackups()/
// pollConfigBackupNow(), backed by each vendor's real config-export
// API. mockConfigBackups removed.

// Templates and Compliance are "coming soon" placeholders for now
// (deliberately not built yet, per product decision) -- no mock data
// needed for either.
