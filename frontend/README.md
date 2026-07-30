# InfraOS Frontend — Enterprise Redesign

A ground-up frontend redesign: enterprise dark-mode UI with a
collapsed/hover-expand left sidebar, top navigation, and dedicated
pages for Dashboard, Traffic Analytics, Logs, Correlation,
Troubleshooting, and Configuration — modeled on tools like Palo Alto
Strata Cloud Manager, Azure Portal, and Grafana.

**No backend changes were made for this redesign.** Every existing
API, the database schema, auth headers, and business logic in
`../backend` are untouched. This is a pure frontend/navigation/UX
rebuild — see `src/api.js` for the (unchanged) endpoints it calls.

## What's real vs. mock

Pages wired to the actual backend (same endpoints as the previous
single-file dashboard):
- **Devices** — onboarding + inventory (`/devices`)
- **Health Status** — per-device CPU/memory/uptime (`/health/:id`)
- **Network Topology** — live graph + drift detection (`/topology/*`)
- **Traffic Logs** (one of the 5 Logs tabs) — real log search (`/logs`)
- **Correlation** — the real diagnostics trace engine (`/diagnostics`),
  presented as a Host → Switch → Router → Firewall → Destination
  timeline
- **Troubleshooting** — same real diagnostics engine, presented as a
  validation workspace (routing/policy/NAT/VLAN checks)
- **CLI** — the real, audited WebSocket terminal (`/cli/ws/:id`),
  now in a three-panel enterprise layout (saved commands / terminal /
  AI-assistant placeholder)
- **Alarms** — real threshold-based alerts (`/alarms`), generated from
  the health/interface data already being polled, not sample data
- **License Status** — real license data pulled from the device itself
  (`/licenses`), not sample data
- **Threat/URL/System Logs** — real, same log pipeline as Traffic Logs
  with `event_type` filtering (`/logs?event_type=threat|url|system`)
- **Sessions** — real, live session/flow lookup direct from the device
  (firewall session tables or Cisco router NetFlow cache)
- **Traffic Analytics** — top talkers/applications/denied traffic, real
  aggregation off logged traffic ranked by actual byte volume
  (`/traffic-analytics`). Link Utilization shows real current per-
  interface Tx/Rx **and now a real historical bandwidth trend chart**
  (`/topology/interfaces/{id}/history`, sampled every ~60s)
- **Configuration Backup** — real config snapshots pulled directly from
  each device (`/config-backups`), with on-demand backup and a
  view-config modal; the Devices page's Backup/View actions are wired
  to the same real endpoints
- **Automation** — real, recurring diagnostics checks (`/automations`):
  save a source/destination flow once, it runs automatically on its
  own schedule using the same trace engine as Correlation, and a
  failing run raises a genuine alarm through the existing alerting
  system (not a separate notification path)
- **Reports** — a real aggregated summary (`/reports/summary`) built
  from every other module's real data (devices, alarms, licenses,
  traffic, automations), with JSON export
- **Settings** — a real, persisted admin/organization profile
  (`/settings/profile`) plus a consolidated license-posture summary

Pages using mock data: none currently carry fabricated sample rows.

**Deliberately deferred** (shown as a "coming soon" empty state, not
mock data and not a placeholder pretending to be real):
- Templates, Compliance

**Static/informational, no backend needed:**
- Support

## Sidebar behavior (the centerpiece)

- Collapsed by default (68px, icons + tooltips only)
- Expands to 272px on hover, as a fixed-position overlay — the main
  content area's left margin never changes, so nothing shifts or
  resizes
- Collapses automatically on mouse-leave
- On screens under 768px: no hover; a hamburger in the top nav opens
  the same component as a slide-out drawer instead
- Nav structure is data-driven (`src/navConfig.js`) — adding a new
  module later is one entry, not a Sidebar code change

## Running it locally

```bash
npm install
npm run dev
```

Talks to the backend at `http://localhost:3100` by default. To point
at a different backend, set `window.INFRAOS_API_BASE` (e.g. in
`index.html` before the app script, or via a small inline script) —
same mechanism the previous frontend used.

## Building

```bash
npm run build   # outputs to dist/
npm run preview # serve the production build locally
```

## Design tokens

See `src/index.css` for the full token list. Summary: near-black
background (`#0B0E13`), a single restrained amber accent (`#E8A33D`)
for active states and primary actions, teal/amber/red reserved
strictly for status (healthy/warning/critical). Inter for UI text,
IBM Plex Mono for tabular/technical data (IPs, CLI output, log
tables) — deliberately no gradients, no glow effects, minimal color
per the brief.
