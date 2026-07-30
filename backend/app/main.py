from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import devices, health, logs, diagnostics, troubleshooting, network_diagram, topology, cli, identities, alarms, licenses, sessions, traffic_analytics, config_backups, reports, settings
from app.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="InfraOS API",
    description="Phase 1+2: Palo Alto + Fortigate firewalls, Cisco IOS "
                 "router + switch. Health monitoring, log search, full "
                 "switch->router->firewall diagnostics, basic topology, "
                 "and full CLI access.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before anything beyond local dev
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices.router)
app.include_router(health.router)
app.include_router(logs.router)
app.include_router(diagnostics.router)
app.include_router(troubleshooting.router)
app.include_router(network_diagram.router)
app.include_router(topology.router)
app.include_router(cli.router)
app.include_router(identities.router)
app.include_router(alarms.router)
app.include_router(licenses.router)
app.include_router(sessions.router)
app.include_router(traffic_analytics.router)
app.include_router(config_backups.router)
app.include_router(reports.router)
app.include_router(settings.router)


@app.on_event("startup")
def _startup():
    start_scheduler()


@app.get("/")
def root():
    return {
        "service": "InfraOS API", "phase": 2,
        "vendors": ["paloalto", "fortigate", "cisco_ios"],
    }
