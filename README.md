# InfraOS — Phase 1 through 8

Palo Alto + Fortigate firewalls, Cisco IOS router + switch. Health
monitoring, log search, topology-aware diagnostics with visual trace
overlay and identity-aware correlation, drift detection, a live topology
canvas, full CLI access with genuine configuration capability and an
audit viewer, real persistent storage (Postgres + Elasticsearch), a
real threshold-based alerting engine, and an enterprise-grade multi-page
frontend redesign.

The monitoring/diagnostics/topology features remain **read-only** — they
never push config or policy changes on their own. The one deliberate
exception is the **full CLI** (web terminal + native client): `config_admin`
and `super_admin` roles can run genuine configuration-mode commands on any
onboarded device, since "full CLI access" was the point from the start.
Every command is recorded to an audit transcript and tagged as config-vs-
read; the frontend and native client both prompt for confirmation before
sending anything that looks like a config change. See "What's new in
Phase 5" below. Original design context:
`/mnt/user-data/outputs/InfraOS-Build-Prompt.md`.

## What's implemented (Phase 1)

- **Normalized data model** (`app/models.py`) — vendor-agnostic Device,
  Interface, Session, PolicyRule, LogEvent, HealthSnapshot, DiagnosticsResult,
  TopologyLink, DiscoveredNeighbor
- **Vendor driver interface** (`app/drivers/base.py`) — the abstract
  contract every vendor plugin implements
- **PaloAltoDriver** (`app/drivers/paloalto.py`) — PAN-OS XML API (facts,
  interfaces, sessions, `test security-policy-match`, logs) + SSH CLI
- **FortigateDriver** (`app/drivers/fortigate.py`) — FortiOS REST API
  (facts, interfaces, policy, logs) + a CLI-based policy-lookup diagnostic
  + SSH CLI
- **Health polling + log ingestion scheduler**, **credential vault stub**,
  **REST API** for onboarding/health/logs

## What's new in Phase 2

- **CiscoIOSRouterDriver + CiscoIOSSwitchDriver** (`app/drivers/cisco_ios.py`)
  — SSH/CLI-based (no clean REST API for most IOS devices in the field),
  sharing a common base class for facts/interfaces/health/neighbors, with
  `get_route` on the router and `get_arp_mac_table` on the switch
- **Driver factory now keys on (vendor, device_type)** (`app/drivers/factory.py`)
  so Cisco router vs switch resolve to the right driver
- **Full diagnostics hop chain** (`app/diagnostics.py`) — switch (ARP/MAC
  presence + port state) → router (route to destination) → firewall
  (policy match + sessions + logs), in that order. Path selection is
  still simplified: it checks every onboarded switch/router/firewall
  rather than walking the actual topology graph to pick the one true
  path — good enough for a single-site test network, worth revisiting
  for multi-site
- **Topology engine** (`app/topology.py`) — manual link creation plus
  CDP/LLDP-based auto-discovery (`get_neighbors()`), kept as two separate
  tagged sets (`manual` vs `discovered`) so drift detection has something
  to compare later (not built yet)
- **Web-based full CLI terminal** (`app/api/cli.py`) — a WebSocket proxy
  to any onboarded device's CLI, with every command + output recorded
  to an audit transcript (`GET /cli/transcript/{device_id}`)
- **Minimal RBAC** (`app/rbac.py`) — a placeholder role system (no login
  flow yet) that at least blocks `read_only_auditor`/`noc_viewer` roles
  from configuration-mode commands in the CLI
- **Native InfraOS CLI client** (`cli_client/infraos_cli.py`) — a small
  script (`infraos device list`, `infraos device ssh <hostname>`,
  `infraos diagnose --src ... --dst ...`) that talks to the API directly,
  using the same audited web-SSH gateway under the hood
- **Frontend**: added Topology and CLI tabs to the dashboard; the CLI tab
  is a real WebSocket terminal

## What's new in Phase 3

- **Live interface stats engine** (`app/link_stats.py`) — polls every
  5 seconds (via the scheduler), computes real Tx/Rx Mbps from raw byte-
  counter deltas between polls (bandwidth isn't a value any API just
  hands you — it's derived from two samples over time). Fortigate and
  Cisco drivers now return real byte counters (`tx_bytes`/`rx_bytes`);
  Palo Alto's `get_interfaces()` op-command doesn't expose counters yet,
  so its Mbps is honestly left as `None` rather than faked — see the
  TODO in `paloalto.py` for what a real implementation needs
- **Extended Interface model** — `admin_status` (enabled/disabled),
  `oper_status` (up/down), `mac_address`, `tx_bytes`/`rx_bytes` (raw),
  `tx_mbps`/`rx_mbps` (computed) — all vendor-agnostic
- **Topology graph API** (`GET /topology/graph`) — everything the visual
  canvas needs in one call: device nodes + links with each endpoint's
  live status and traffic
- **Interface auto-fetch** (`GET /topology/interfaces/{device_id}`) —
  when defining a link, the admin picks a device + interface from a
  dropdown; IP and MAC are already fetched and shown, never typed in
  by hand
- **Sci-fi visual topology canvas** (originally `frontend/index.html`,
  now `frontend-legacy-single-file/index.html` — superseded by the
  Phase 7 redesign, `TopologyTab`)
  — dark grid backdrop, glowing nodes, and links color-coded by state
  (teal glow = up, red glow = down, dashed gray = disabled), with an
  animated dashed-line "flow" effect on active links and live Tx/Rx
  Mbps labels. Auto-layers devices left-to-right based on how links are
  defined (LAN-side devices end up on the left, WAN/firewall-side on
  the right, whatever order that turns out to be for your network) using
  a topological-sort-style layering — no manual dragging required.
  Refreshes every 5 seconds to match the backend poller.

## What's new in Phase 4

- **Topology-based path selection** (`app/path_selection.py`) — the
  diagnostics engine now walks the *actual wired path*: it finds which
  onboarded switch the source IP is really connected to (via the ARP/MAC
  table), then follows the topology graph link-by-link until it reaches
  a firewall. Only falls back to "check every onboarded switch/router/
  firewall" (the Phase 2/3 behavior) when there isn't enough topology
  data yet — nothing wired up, or the source IP isn't seen anywhere.
  The API response now includes `path_source` (`"topology"` or
  `"fallback-all-devices"`) so it's always clear which mode ran.
- **Drift detection** (`app/drift.py`, `GET /topology/drift`) — compares
  the manually-drawn topology against what CDP/LLDP discovery actually
  finds and flags three kinds of mismatch: a manual link never seen live,
  a discovered link that was never drawn, and a link that exists in both
  but on different interfaces than expected. Surfaced as a red panel in
  the Topology tab.
- **Visual trace overlay** — running a diagnostics trace now highlights
  the exact devices and links it walked directly on the topology canvas
  (amber outline/glow), with a "View traced path on topology" button
  that jumps you there. Makes the connection between "why is this
  broken" and "where, physically, is it broken" immediate.

## What's new in Phase 5

- **Full CLI can now genuinely edit and configure any onboarded device**
  — this was mechanically already possible since Phase 2 (the CLI is a
  real, persistent SSH shell, not a restricted show-only one), but Phase 5
  makes it a first-class, audited feature rather than an incidental side
  effect:
  - `app/rbac.py` now exposes `is_config_command()` as a shared classifier,
    used both to block `noc_viewer`/`read_only_auditor` roles from config
    commands and to tag every command in the audit transcript (`is_config:
    true/false`) regardless of who ran it or what role they had
  - Per-vendor quick-action commands (`GET /cli/quick-commands/{device_id}`)
    — "enter config mode" and "save/commit config" map to the right
    command for each vendor (`configure terminal` + `write memory` for
    Cisco, `configure` + `commit` for PAN-OS, `config global` + `end` for
    FortiOS) so the admin doesn't have to remember vendor-specific syntax
  - The web terminal and native CLI client both prompt for confirmation
    before sending anything classified as a config command, and visually
    tag config commands in the terminal output (`[CONFIG]`)
- **What's still out of scope**: the *automated* platform features
  (security policy creation via the API, config templates, bulk config
  push) are unchanged and still read-only/not built -- this phase is
  specifically about the human-driven CLI, where an admin who already has
  device credentials and config_admin/super_admin access is directly
  typing commands themselves, with the platform brokering the connection
  and keeping the audit trail. That's a materially different risk profile
  than an automated system generating and pushing config changes on its
  own, which is why the two were deliberately kept separate.

## What's new in Phase 6

- **Real persistent storage** — `app/store.py` is now backed by
  SQLAlchemy (Postgres in production, SQLite locally — same code either
  way) instead of an in-memory object. Devices, health history,
  diagnostics history, topology links, CLI transcripts, live interface
  stats, and identities all survive a restart. Verified with dedicated
  tests (`test_persistence.py`) that write through one `Store()` instance
  and read back from a second, independent one — proving it's really the
  database, not a process-local cache.
- **Elasticsearch for logs** (`app/log_store.py`) — logs go to
  Elasticsearch when `INFRAOS_ELASTICSEARCH_URL` is set, with a
  transparent in-memory fallback for local dev without a running ES
  instance. Nothing else in the codebase knows which backend is active.
- **Docker Compose** (`docker-compose.yml`) — the full stack (Postgres +
  Elasticsearch + backend + frontend via nginx) in one `docker compose up`.
  See `.env.example` for the environment variables a real deployment needs.
- **Identity-aware correlation** (`app/api/identities.py`) — a manual
  username↔IP/MAC binding API (no AD/LDAP or DHCP-lease integration yet)
  that the diagnostics engine now uses: the verdict names the person
  ("blocked for vish (10.1.1.5)") when a binding is known, not just the
  IP, which is what breaks the moment DHCP reassigns an address.
- **CLI audit viewer** — a new Audit tab in the dashboard, backed by
  `GET /cli/audit`, lets you search everything anyone has run across every
  device, filter to configuration changes only, or scope to one admin or
  one device.

## What's new in Phase 7

- **Enterprise frontend redesign** (`frontend/`) — the single-file
  sci-fi dashboard was replaced with a proper multi-page React app
  (Vite + react-router + recharts + lucide-react): a collapsed/hover-
  expand left sidebar that overlays without shifting content, a sticky
  top nav, and dedicated pages for Dashboard, Traffic Analytics, Logs
  (5 tabs), Correlation, Troubleshooting, Configuration (Devices/
  Templates/CLI/Backup), and placeholder pages for Automation/
  Compliance/Reports/Settings/Support. See `frontend/README.md` for
  the full real-vs-mock breakdown.
- **No backend changes** — this was a frontend-only redesign, per the
  request. Every API endpoint, the database schema, RBAC, and business
  logic in `backend/` are exactly as Phase 6 left them (confirmed: all
  56 backend tests still pass unchanged).
- **The old single-file frontend is kept** at
  `frontend-legacy-single-file/` for reference — nothing there was
  deleted, just superseded as the primary UI.
- **Docker Compose updated** — the frontend service now builds via a
  proper multi-stage Dockerfile (Vite build → nginx) instead of
  mounting a static HTML file, since the frontend is a real build-step
  app now.

## What's new in Phase 8 — converting mock sections to real, one at a time

Started working through the frontend's mock-data sections, converting
each to a genuinely real backend feature rather than leaving them as
sample data. First one done:

- **Alarms — now real** (`app/alerting.py`, `GET /alarms`, `GET /alarms/summary`):
  a threshold engine that runs off data already being polled — no new
  vendor calls needed. CPU/memory thresholds evaluated right after every
  60s health poll; interface-down alarms evaluated right after every 5s
  interface-stats poll. An alarm is created the same cycle a threshold
  is crossed, and resolved the same cycle it clears (not a separate
  cron re-scanning stale data). Escalation is handled (a medium CPU
  alarm becomes critical without creating a duplicate row), and repeated
  polls at the same severity don't spam new alarms. 10 dedicated tests,
  plus an API smoke test proving the whole path — poll → alert →
  API response — works end to end. The frontend's dashboard Active
  Alarms table and Critical/Active Alarm summary cards are now wired to
  this; the `mockAlarms` data was deleted, not just unused.
- **License Status — now real** (`GET /licenses`, `POST /licenses/{id}/poll-now`):
  Palo Alto's driver uses the real `request license info` op-command
  (feature name, expiry date, expired flag, parsed from actual PAN-OS
  XML). Fortigate's driver uses the real `/monitor/license/status`
  endpoint, parsed generically across license bundles since FortiOS's
  exact field names shift by version (flagged in the code for
  verification against your instance). Polled every 6 hours plus an
  on-demand poll-now endpoint. Cisco IOS has no license driver yet, so
  Cisco devices simply don't appear in license data — not an error,
  just not implemented. 10 new tests, full suite at 74 passing. The
  frontend's License Status page and dashboard card are wired to this;
  `mockLicenses` was deleted from `mockData.js`.
- **Threat/URL/System Logs — now real** (`GET /logs?event_type=...`):
  extended the same real log pipeline that already backed Traffic Logs
  to the other three types. PAN-OS uses the same log API with a
  different `log-type` parameter (traffic/threat/url/system — all real
  PAN-OS values); FortiOS splits them across separate disk-log
  endpoints (`log/disk/ips` for threat, `log/disk/webfilter/webfilter`
  for URL, `log/disk/event/system` for system — field names flagged in
  the code for verification against your FortiOS version, same honesty
  pattern as License Status). Cisco IOS routers/switches don't generate
  threat or URL logs (that's a firewall/UTM feature) — requesting those
  from a Cisco device now honestly returns nothing rather than
  fabricating data, same principle as the license gap. The scheduler
  now polls all four log types per device, not just traffic. 8 new
  driver tests + 2 log-store tests, full suite at 82 passing. The
  frontend's Threat/URL/System log tabs are wired to the real API with
  a shared search component (`LogSearchTab`); `mockThreatLogs`/
  `mockUrlLogs`/`mockSystemLogs` were deleted from `mockData.js`.
- **Traffic Analytics — now real** (`GET /traffic-analytics`,
  `app/traffic_analytics.py`): top source IPs, top destination IPs, and
  top applications are aggregated from real TRAFFIC-type logs already
  in the log store, ranked by actual byte volume — not hit count
  pretending to be volume. That required two new real fields on
  `LogEvent`: `bytes_total` (PAN-OS's real `bytes` field, FortiOS's
  `sentbyte`+`rcvdbyte` summed) and `matched_rule` (PAN-OS's `rule`
  field, FortiOS's `policyname`/`policyid`) — both parsed from real
  vendor log data, both tested. Denied Traffic groups by real
  destination + the real matched rule. A dashboard "Total Traffic"
  card now sums real bytes across the window instead of showing a
  fixed mock number. **Link Utilization is real but scoped down
  honestly**: it shows real current Tx/Rx per interface (the same live
  data the topology canvas uses), but there's no historical trend chart
  yet — the backend only keeps the latest interface snapshot, not a
  time series, so a bandwidth-over-time graph would have nothing real
  to plot. That's flagged directly in the page copy rather than faked
  with a chart. 6 new aggregation tests + 4 new driver-parsing tests
  (bytes/rule fields), full suite at 92 passing. `mockTrafficTrend`/
  `mockTopSourceIps`/`mockTopDestinations`/`mockTopApplications`/
  `mockDeniedDestinations` all deleted from `mockData.js`.
- **Link Utilization now has real history** — `InterfaceStatHistoryRow`
  is a genuine time series (unlike `InterfaceStatRow`, which only ever
  holds the latest snapshot), sampled every ~60s by downsampling the
  5s live poll (recording every 5s would add ~17k rows/day per
  interface for no real chart-resolution benefit). New endpoint:
  `GET /topology/interfaces/{id}/history`. The Link Utilization page
  now shows a real bandwidth-over-time chart for whichever interface
  you click. 4 new tests.
- **Configuration Backup — now real** (`GET /config-backups`,
  `POST /config-backups/{id}/poll-now`): real `get_running_config()` on
  all three drivers — PAN-OS's `show config running` op-command,
  FortiOS's real `/monitor/system/config/backup` endpoint (the same one
  the GUI's "Backup Configuration" button uses), Cisco's `show
  running-config`. Backups accumulate as real history (unlike
  license/interface state, which only track "current") so you can
  browse past snapshots, not just the latest. Polled daily, plus
  on-demand via poll-now. The Devices inventory page's Backup/View
  actions are wired to this too — no more placeholder buttons. 7 new
  tests (3 driver-parsing + 4 store), full suite at 103 passing.
  `mockConfigBackups` deleted.
- **Router/switch licensing, application-based logs, router session/
  flow data** — three targeted enhancements:
  - **Cisco Smart Licensing** (`CiscoIOSDriverBase.get_licenses()`):
    real `show license status` + `show license summary` parsing for
    both routers and switches. Expiry is honestly `None` — Smart
    Licensing doesn't expose a clean per-feature expiry the way
    PAN-OS/FortiOS do.
  - **Application field on logs** (`LogEvent.app`): threaded through
    the log store, API (`GET /logs?app=...`), and both firewall
    drivers (PAN-OS's real `app` field, FortiOS's `app`/`service`
    field). Traffic and Threat log tabs now show and filter by
    application.
  - **Router session/flow data** (`CiscoIOSRouterDriver.get_sessions()`):
    parses Cisco's real classic NetFlow cache (`show ip cache flow`,
    including its hex-encoded ports/protocol) — the router-side
    equivalent of a firewall's session table. Wired into the
    diagnostics engine's router hop, so a route now says "confirmed in
    the flow/session cache" when a matching flow exists, not just "a
    route exists." Also exposed directly via a new `GET /sessions/
    {device_id}` endpoint and a new Sessions tab in the frontend, for
    manual correlation independent of running a full trace. 6 new
    tests across these three additions.
- **Templates and Compliance — deliberately deferred, shown as
  "coming soon"** rather than built half-real or left as mock tables.
  Templates in particular had a working mock page before this; it's
  been removed rather than kept around as a distraction.
- **Automation — built as its own real feature, not a copy of
  Correlation with a schedule bolted on.** The distinguishing idea:
  a saved automation check is a real, recurring version of the
  diagnostics trace (same engine as Correlation/Troubleshooting), but
  a *failing* run raises a genuine Alarm through the existing alerting
  system (`app/automation.py`) and clears it automatically when the
  path recovers — so a regression shows up in the same place CPU/
  memory/interface alarms already do, instead of a separate list
  someone has to remember to check. New tables (`automation_checks`,
  `automation_runs`), a 30s scheduler tick that respects each check's
  own interval, and a full CRUD + run-history API (`/automations`).
  11 new tests (4 store + 7 execution engine, including the alarm
  create/resolve integration).
- **Reports — real aggregation, not a new data source.** `GET
  /reports/summary` assembles device counts, alarm counts, licenses
  expiring soon, real traffic totals, and automation health from the
  modules already built — deliberately no independent report data of
  its own, since faking report content would be worse than not having
  reports at all. JSON export from the frontend. 4 new tests.
- **Settings — a real, persisted admin/org profile** (name, email,
  organization), since there's no multi-user login system to hang a
  "Settings" page off of yet (the RBAC placeholder is still just
  headers — see the warnings elsewhere in this doc). Also surfaces a
  real consolidated license-posture summary. Covered by the same store
  tests as Automation above.
- Full suite at 119 passing after every item above.

## Running it locally

### Docker Compose (full stack)

```bash
docker compose up --build
```

This runs Postgres, Elasticsearch, the backend, and the frontend via
nginx. The frontend nginx container reverse-proxies all API/WebSocket
traffic to the backend (see `frontend/nginx.conf`), so the browser only
ever talks to the frontend's own origin -- no backend host/port is
baked into the JS bundle, and the same build works unmodified whether
you're on `localhost` or a real deployed host/IP.

Visit **`http://<your-host>:3110`** (e.g. `http://localhost:3110`
locally, or `http://<server-ip>:3110` on a remote box) -- that's the
only port that needs to be reachable from outside. Backend is at
`3100` (direct API access/`docs`), Postgres on `5432`, Elasticsearch on
`9200`; those don't need to be exposed publicly, only to each other on
the compose network.

### Backend only (local, no Docker)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 3100
```

The API is now at `http://localhost:3100` (interactive docs at `/docs`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs at `http://localhost:3120`. Calls relative API paths (`/devices`,
etc.); Vite's dev-server proxy (`vite.config.js`) forwards these to
`http://localhost:3100` locally, mirroring what nginx does in
production -- so the exact same frontend code/build works in both
places without an env var or rebuild. See `frontend/README.md`
for the full page-by-page breakdown and how to point at a different
backend. The old single-file version still works too, unchanged, at
`frontend-legacy-single-file/index.html`.

### Native CLI client

```bash
pip install requests websocket-client
python cli_client/infraos_cli.py device list
python cli_client/infraos_cli.py device ssh edge-fw-01
python cli_client/infraos_cli.py diagnose --src 10.1.1.5 --dst 157.240.1.1 --port 443
```

### Tests

```bash
cd backend
PYTHONPATH=. pytest tests/ -v
```

119 tests, all passing across every driver, the diagnostics engine,
topology/drift/path-selection, RBAC, persistence, alerting, license
and log storage, traffic analytics, interface-stat history,
config-backup storage, automation execution (including alarm
integration), and reports aggregation. Tests run against an isolated
in-memory SQLite database (see `tests/conftest.py`) regardless of what
`INFRAOS_DATABASE_URL` is set to locally.

## Testing against real devices

You'll need your own lab or trial-license Palo Alto (PAN-OS), Fortigate
(FortiOS), and Cisco IOS/IOS-XE devices — this environment has no network
path to real network hardware, so every driver here is written against
documented APIs/CLI output and unit-tested with mocked responses, but
**has not been exercised against live hardware**. Before trusting any of
this:

1. Onboard a real device of each type and confirm `get_facts()` returns
   the right model/serial/OS version.
2. Verify `test_policy_match` (Palo Alto and Fortigate) against a known
   allow rule and a known deny rule, cross-checked against the device's
   own admin UI.
3. Verify Cisco `get_route` and `get_arp_mac_table` output parsing against
   your actual IOS/IOS-XE version — the regexes in `cisco_ios.py` target
   a mainstream 17.x release and commonly drift across versions/platforms.
4. Verify CDP neighbor parsing (`get_neighbors`) — if your network uses
   LLDP instead of CDP, swap the command (`show lldp neighbors detail`)
   and adjust the regex.
5. FortiOS's CLI-based policy lookup (`diagnose firewall iprope lookup`)
   should be checked against your exact FortiOS version — output format
   has changed across major releases.
6. Test the web-SSH terminal and native CLI client against a real device
   and confirm the audit transcript (`GET /cli/transcript/{device_id}`)
   captures what you expect.

## Known simplifications (intentional)

- **In-memory store** (`app/store.py`) instead of Postgres/Elasticsearch —
  swapping this out only touches this one file, nothing else, by design.
  Data (including topology links and CLI transcripts) is lost on restart;
  fine for local testing, not for anything beyond it.
- **Diagnostics checks every onboarded switch/router/firewall**, not just
  the ones on the actual path — real topology-graph-based path selection
  (walking `TopologyLink`s from source to destination) is a good next
  refinement once there's more than one switch/router/firewall in the lab.
- **No drift detection yet** — manual and CDP/LLDP-discovered topology
  links are both stored and both visible in the Topology tab, but nothing
  compares them and flags mismatches yet.
- **RBAC is still a placeholder, and this matters more now** (`app/rbac.py`)
  — there's no login flow; roles are passed as headers by whatever sits in
  front of this API, which means anyone who can reach the API can claim
  `config_admin` and get genuine configuration access to every onboarded
  device. This was a reasonable placeholder when everything was read-only;
  now that the CLI can make real changes, replacing this with real
  session/JWT auth before exposing this beyond a trusted local network
  is not optional.
- **PAN-OS log query is simplified to a single synchronous call** — real
  PAN-OS log queries are async (submit a job, poll until `status=FIN`);
  production code should implement that polling loop instead of assuming
  results are ready immediately.
- **CORS is wide open (`*`)** — fine for local dev, tighten before any
  shared/hosted deployment.

- **Palo Alto has no live Tx/Rx yet** — its interface op-command doesn't
  return byte counters; a real implementation needs the separate
  `show counter interface <if>` op-command wired into `get_interfaces()`.
- **Topology layout is a simple layering heuristic**, not a physical
  diagram — it orders devices left-to-right by link direction; it
  doesn't know real cable lengths or rack positions.
- **Path selection is a graph walk, not shortest-path routing** — it
  works correctly for the common single-path chain topology this design
  targets (one switch → one router → one firewall), but for a network
  with redundant links or multiple firewalls it takes the first
  unvisited neighbor rather than computing the actual lowest-cost path.
  Fine for a single-site test network; revisit with real path-cost
  routing for anything with redundancy.
- **Drift detection compares device pairs, not link count** — if there
  are ever two physical links between the same two devices, this
  doesn't yet distinguish which is which.
- **No DB migrations** — `init_db()` just calls `create_all`, which
  creates missing tables but doesn't handle schema changes to existing
  ones. Fine for the MVP; a real deployment should move to Alembic
  before the schema changes again.
- **Identity bindings are entirely manual** — there's no AD/LDAP or
  DHCP-lease integration populating them yet, so identity-aware
  correlation only works for IPs someone has explicitly registered via
  `POST /identities`.

## Next: Phase 7+

Real session/JWT auth to replace the RBAC placeholder (still the most
important gap — it's a bigger problem now that both config changes and a
real database are involved), Palo Alto byte counters for full Tx/Rx
parity, shortest-path routing for topologies with redundancy, DB
migrations via Alembic, and an actual AD/LDAP or DHCP-lease feed for
identity correlation instead of the manual API.
