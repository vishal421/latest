#!/usr/bin/env python3
"""
Native InfraOS CLI client -- talks to the InfraOS API so admins can
script bulk operations or open a device shell from their own terminal,
instead of only clicking through the web dashboard.

Usage:
    infraos device list
    infraos device ssh <hostname>
    infraos diagnose --src 10.1.1.5 --dst 157.240.1.1 --port 443

Requires: requests, websocket-client
    pip install requests websocket-client
"""
from __future__ import annotations

import argparse
import sys

import requests

DEFAULT_API_BASE = "http://localhost:3100"


def cmd_device_list(args):
    resp = requests.get(f"{args.api_base}/devices")
    resp.raise_for_status()
    devices = resp.json()
    if not devices:
        print("No devices onboarded.")
        return
    print(f"{'HOSTNAME':<20}{'VENDOR':<14}{'TYPE':<10}{'MGMT IP':<16}{'MODEL'}")
    for d in devices:
        print(f"{d['hostname']:<20}{d['vendor']:<14}{d['device_type']:<10}{d['mgmt_ip']:<16}{d.get('model', '')}")


def cmd_device_ssh(args):
    """Opens an interactive shell to the named device through the
    InfraOS web-SSH gateway (same audited session the browser terminal
    uses -- commands are recorded server-side either way, tagged as
    config-vs-read regardless of role)."""
    import websocket  # websocket-client

    CONFIG_KEYWORDS = ("configure", "conf t", "set ", "delete ", "commit", "edit ", "no ", "write memory", "copy running-config", "clear ")

    resp = requests.get(f"{args.api_base}/devices")
    resp.raise_for_status()
    devices = resp.json()
    match = next((d for d in devices if d["hostname"] == args.hostname), None)
    if not match:
        print(f"No onboarded device named '{args.hostname}'", file=sys.stderr)
        sys.exit(1)

    ws_base = args.api_base.replace("http", "ws", 1)
    ws_url = f"{ws_base}/cli/ws/{match['device_id']}?admin_user={args.user}&role={args.role}"
    ws = websocket.create_connection(ws_url)
    print(ws.recv())  # connection banner
    print(f"Connected to {args.hostname}. Type 'exit' to quit.")
    try:
        while True:
            command = input(f"{args.hostname}# ")
            if command.strip() in ("exit", "quit"):
                break
            if any(command.strip().lower().startswith(kw) for kw in CONFIG_KEYWORDS):
                confirm = input(f"This looks like a config change: '{command}'. Send? [y/N] ")
                if confirm.strip().lower() != "y":
                    continue
            ws.send(command)
            print(ws.recv())
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        ws.close()


def cmd_diagnose(args):
    resp = requests.post(
        f"{args.api_base}/diagnostics",
        json={"src_ip": args.src, "dst_ip": args.dst, "port": args.port, "protocol": args.protocol},
    )
    resp.raise_for_status()
    result = resp.json()
    for hop in result["hops"]:
        status = "PASS" if hop["passed"] else "FAIL"
        print(f"[{status}] {hop['hop_type']:<9} {hop['device_id']:<16} {hop['reason']}")
    print()
    print(f"Root cause: {result['verdict']}")


def main():
    parser = argparse.ArgumentParser(prog="infraos", description="Native InfraOS CLI client")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="InfraOS API base URL")
    sub = parser.add_subparsers(dest="command", required=True)

    device_parser = sub.add_parser("device", help="device operations")
    device_sub = device_parser.add_subparsers(dest="device_command", required=True)

    device_sub.add_parser("list", help="list onboarded devices").set_defaults(func=cmd_device_list)

    ssh_parser = device_sub.add_parser("ssh", help="open a full CLI session to a device")
    ssh_parser.add_argument("hostname")
    ssh_parser.add_argument("--user", default="cli-user", help="admin identity recorded in the audit log")
    ssh_parser.add_argument("--role", default="config_admin", choices=["super_admin", "config_admin", "noc_viewer", "read_only_auditor"])
    ssh_parser.set_defaults(func=cmd_device_ssh)

    diag_parser = sub.add_parser("diagnose", help="run the automated traffic-flow trace")
    diag_parser.add_argument("--src", required=True, help="source IP")
    diag_parser.add_argument("--dst", required=True, help="destination IP")
    diag_parser.add_argument("--port", type=int, default=443)
    diag_parser.add_argument("--protocol", default="tcp", choices=["tcp", "udp"])
    diag_parser.set_defaults(func=cmd_diagnose)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
