"""
Browser-based full CLI access, proxied through the backend so the
admin never sees raw device credentials directly. Every command and
its output is recorded to the store for audit, tagged as config-vs-
read (Section F / Module I of the design doc) -- this is genuinely
unrestricted access for config_admin/super_admin, including
configuration-mode commands. Read-only roles are blocked from those
same commands (see app/rbac.py).

This is a WebSocket, not a REST endpoint, since a terminal is
inherently a two-way interactive stream: the browser sends keystrokes/
commands, the backend relays them to the device over the driver's
CLISession and streams output back.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from app.store import store
from app.drivers.factory import get_driver
from app.rbac import check_command_allowed, is_config_command, CONFIG_MODE_ENTRY, SAVE_CONFIG_COMMAND

router = APIRouter(prefix="/cli", tags=["cli"])


@router.websocket("/ws/{device_id}")
async def cli_websocket(
    websocket: WebSocket,
    device_id: str,
    admin_user: str = "unknown",
    role: str = "read_only_auditor",
):
    device = store.get_device(device_id)
    if not device:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    driver = get_driver(device)
    try:
        driver.connect()
        session = driver.open_cli_session()
    except Exception as exc:  # noqa: BLE001 -- tell the admin why the connection failed instead of the socket just dying
        await websocket.send_text(f"[connection failed] {exc}\n")
        await websocket.close(code=1011)
        return

    try:
        await websocket.send_text(f"-- connected to {device.hostname} ({device.vendor.value}) as {admin_user} --\n")
        while True:
            command = await websocket.receive_text()
            try:
                check_command_allowed(role, command)
            except PermissionError as exc:
                await websocket.send_text(f"[denied] {exc}\n")
                continue

            try:
                output = session.send_command(command)
            except ConnectionError as exc:
                # The SSH session itself is gone (device closed it, a
                # keepalive probe failed, etc.) -- tell the admin why
                # instead of the terminal just going dead, and end the
                # session cleanly so the frontend can offer reconnect.
                await websocket.send_text(f"[disconnected] {exc}\n")
                break
            except Exception as exc:  # noqa: BLE001 -- one bad command shouldn't kill the whole session
                await websocket.send_text(f"[error] {exc}\n")
                continue

            store.record_cli_command(device_id, admin_user, command, output, is_config=is_config_command(command))
            await websocket.send_text(output)
    except WebSocketDisconnect:
        pass
    finally:
        session.close()


@router.get("/transcript/{device_id}")
def get_transcript(device_id: str):
    """Audit trail for a device's CLI sessions -- every command run,
    its output, who ran it, and whether it was a configuration change,
    with a timestamp."""
    if not store.get_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return store.get_cli_transcript(device_id)


@router.get("/audit")
def search_audit(device_id: str | None = None, admin_user: str | None = None, config_only: bool = False, limit: int = 200):
    """Cross-device audit search -- the CLI transcript viewer's data
    source. Unlike /transcript/{device_id}, this isn't scoped to one
    device, so it's what backs an 'all config changes this week'
    or 'everything this admin ran' view."""
    return store.search_cli_transcripts(device_id=device_id, admin_user=admin_user, config_only=config_only, limit=limit)


class QuickCommandsResponse(BaseModel):
    enter_config_mode: str | None
    save_config: str | None


@router.get("/quick-commands/{device_id}", response_model=QuickCommandsResponse)
def get_quick_commands(device_id: str):
    """The right 'enter config mode' and 'save/commit' command for this
    device's vendor -- surfaced as quick-action buttons in the CLI tab
    so the admin doesn't have to remember that PAN-OS uses `commit`,
    Cisco uses `write memory`, and so on."""
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    vendor_key = device.vendor.value
    return QuickCommandsResponse(
        enter_config_mode=CONFIG_MODE_ENTRY.get(vendor_key),
        save_config=SAVE_CONFIG_COMMAND.get(vendor_key),
    )
