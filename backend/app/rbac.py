"""
Minimal RBAC for the MVP. This is a placeholder, not a real auth
system -- there's no login flow yet, so the "admin" identity and role
are passed as headers by whatever sits in front of this API (a real
deployment would replace this with proper session/JWT auth and pull
the role from there).

Roles (from the design doc): super_admin, config_admin, noc_viewer,
read_only_auditor. The CLI gateway (app/api/cli.py) gives config_admin
and super_admin genuine, unrestricted device access -- including
configuration-mode commands -- since "full CLI access" was always the
point. noc_viewer and read_only_auditor are blocked from anything that
looks like a config-mode command, and every command (from any role) is
tagged as config-vs-read in the audit transcript so config changes are
always identifiable after the fact, regardless of who ran them.
"""
from __future__ import annotations

from fastapi import Header, HTTPException

READ_ONLY_ROLES = {"read_only_auditor", "noc_viewer"}
FULL_CLI_ROLES = {"super_admin", "config_admin"}
ALL_ROLES = READ_ONLY_ROLES | FULL_CLI_ROLES

# Very rough heuristic -- a real implementation should use each
# vendor's own "would this command change config" classification
# rather than a keyword list. Used two ways: (1) to block read-only
# roles from running these, (2) to tag every command in the audit
# transcript as a config change regardless of role, so "what changed
# and who changed it" is always answerable later.
CONFIG_MODE_KEYWORDS = (
    "configure", "conf t", "set ", "delete ", "commit", "edit ",
    "no ", "write memory", "copy running-config", "clear ",
)

# Per-vendor helpers surfaced in the frontend as quick-action buttons --
# entering config mode and persisting a change look different on every
# vendor, so the platform doesn't guess: it offers the right command for
# whichever device the admin is connected to.
CONFIG_MODE_ENTRY = {
    "cisco_ios": "configure terminal",
    "paloalto": "configure",
    "fortigate": "config global",
}
SAVE_CONFIG_COMMAND = {
    "cisco_ios": "write memory",
    "paloalto": "commit",
    "fortigate": "end",  # FortiOS applies each config block on `end`; nothing extra to persist
}


def is_config_command(command: str) -> bool:
    lowered = command.strip().lower()
    return any(lowered.startswith(kw) for kw in CONFIG_MODE_KEYWORDS)


def get_identity(
    x_infraos_user: str = Header(default="unknown"),
    x_infraos_role: str = Header(default="read_only_auditor"),
) -> tuple[str, str]:
    if x_infraos_role not in ALL_ROLES:
        raise HTTPException(status_code=403, detail=f"Unknown role: {x_infraos_role}")
    return x_infraos_user, x_infraos_role


def check_command_allowed(role: str, command: str) -> None:
    if role in FULL_CLI_ROLES:
        return
    if is_config_command(command):
        raise PermissionError(f"Role '{role}' is not permitted to run configuration-mode commands")
