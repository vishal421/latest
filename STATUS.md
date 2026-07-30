# InfraOS — Feature Status (as of Phase 5)

## Built and working (51 tests passing)

### Core architecture
- Normalized, vendor-agnostic data model (Device, Interface, Session, PolicyRule, LogEvent, TopologyLink, etc.)
- Abstract vendor driver interface — one contract every vendor plugin implements
- Driver factory keyed on (vendor, device_type)
- Credential vault (encrypted at rest, local dev-grade)

### Vendor coverage
- Palo Alto (PAN-OS) — facts, interfaces, sessions, policy-match test, logs, CLI
- Fortigate (FortiOS) — facts, interfaces, policy rules, CLI-based policy lookup, logs, CLI
- Cisco IOS/IOS-XE — router (routes) + switch (ARP/MAC), facts, interfaces + byte counters, CDP neighbors, CLI

### Monitoring & visibility
- Device onboarding (manual, auto-populates facts on add)
- Health polling every 60s (CPU, memory, uptime, session count)
- Log ingestion every 120s + search API (device/src/dst/action/time filters)
- Live interface stats every 5s — real Tx/Rx Mbps from byte-counter deltas (Cisco + Fortigate; Palo Alto pending, see gaps)

### Diagnostics
- Automated switch → router → firewall trace ("why can't this user reach X")
- Topology-based path selection (walks the real wired path via ARP lookup + graph traversal)
- Fallback to check-everything when topology data is insufficient
- `path_source` field always tells you which mode ran

### Topology
- Manual link definition with auto-fetched interface IP/MAC (never typed by hand)
- CDP/LLDP auto-discovery
- Drift detection — manual vs. discovered mismatches (missing either side, or interface mismatch)
- Sci-fi visual canvas: auto-layered layout, color-coded link/port state (up/down/disabled), animated live traffic flow, diagnostics trace overlay highlighting

### Full CLI access
- Browser-based web terminal (WebSocket, real unrestricted shell)
- Native `infraos` CLI client (device list, ssh, diagnose)
- Genuine configuration/edit capability for `config_admin`/`super_admin`
- Per-vendor quick commands (enter config mode, save/commit)
- Every command audit-logged and tagged config-vs-read
- Confirmation prompts before sending config changes (web + native client)
- Minimal RBAC (role-gated, header-based placeholder)
- **CLI audit viewer** — searchable dashboard tab (`GET /cli/audit`): filter by device, admin, config-only

### Persistence (Phase 6)
- Postgres (via SQLAlchemy) backing devices, health history, diagnostics history, topology links, CLI transcripts, live interface stats, and identities — survives a restart, verified by dedicated cross-instance tests
- Elasticsearch backing logs, with a transparent in-memory fallback for local dev
- Docker Compose running the full stack (Postgres + Elasticsearch + backend + nginx-served frontend)

### Identity-aware correlation (Phase 6)
- Manual username↔IP/MAC binding API (`POST /identities`, `GET /identities/resolve`)
- Diagnostics verdict now names the person when a binding is known, not just the IP

---

## What still needs to be added

### Security-critical (should come before any real/shared deployment)
- **Real authentication** — RBAC is currently just headers with no login; anyone reaching the API can claim `config_admin`. Needs real session/JWT auth. This is the single most important gap now that the CLI can make real changes AND a real database is involved.
- **Testing against real hardware** — every driver is unit-tested against mocked responses only, never exercised against a live Palo Alto/Fortigate/Cisco box.
- **DB migrations** — schema changes currently rely on `create_all`, which only adds missing tables. Needs Alembic before the schema changes again.

### Vendor completeness
- **Palo Alto byte counters** — its interface call doesn't return Tx/Rx; needs the separate `show counter interface` op-command wired in for traffic parity with the other two vendors.
- **Access points** — in the original feature list, never built. No AP vendor has a driver yet.
- **Additional vendors** — Juniper, Aruba, other switch/router lines, if this needs to cover more than Palo Alto/Fortigate/Cisco.

### Diagnostics & topology
- **Shortest-path routing** — current path selection is a simple graph walk (first unvisited neighbor), correct for a single chain topology but not real lowest-cost routing for networks with redundant links or multiple firewalls.
- **Alerting** — health/log data is collected but there's no threshold-based alert engine (email/Slack/webhook) yet, despite being in the original design.
- **Real identity feed** — the identity API is manual-entry only; no AD/LDAP or DHCP-lease integration populates it automatically yet.

### Platform / commercial-readiness
- **Multi-tenancy** — single environment only right now; needed if this will be sold to multiple orgs, not just used internally.
- **Automated config-push / policy creation** — deliberately still out of scope. The CLI lets a human type commands directly (audited); there's no automated "create this firewall rule from the UI" feature yet — that was always flagged as the highest-risk phase, needing staged changes/approval workflow/rollback.
- **Change-impact simulation, ticket-to-trace integration, conversational interface over diagnostics** — the "differentiating features" discussed earlier, none built yet.
