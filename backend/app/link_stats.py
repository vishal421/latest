"""
Live interface stats.

Bandwidth (Mbps) isn't something any vendor API just hands you --
it's derived by sampling the raw byte counter twice and dividing the
delta by the time elapsed. This module holds the previous sample per
(device_id, if_name) and computes the rate on each new poll.

Only drivers that actually return tx_bytes/rx_bytes populate real
Mbps here. As of Phase 9 all three vendors do (Fortigate and Cisco
from their respective interface calls; Palo Alto from the separate
`show counter interface all` op-command in paloalto.py). If a call
fails or a device/version doesn't support it, a driver can still
legitimately return tx_bytes/rx_bytes as None for a given interface --
this function keeps handling that gracefully rather than assuming
every vendor always has counters.

The *live* snapshot (store.set_interface_stats) is overwritten every
5s poll, for the topology canvas. A *history* sample (store.
add_interface_stat_samples) is only appended every HISTORY_SAMPLE_EVERY_N_POLLS
polls (60s by default) -- recording history every 5s would grow the
table by ~17,000 rows/day per interface for no real chart-resolution
benefit; a real bandwidth trend doesn't need finer than ~1min buckets.
"""
from __future__ import annotations

from datetime import datetime

from app.models import Interface
from app.drivers.factory import get_driver
from app.store import store
from app.alerting import check_interface_alarms

_previous_samples: dict[tuple[str, str], tuple[int, int, datetime]] = {}  # (device_id, if_name) -> (tx_bytes, rx_bytes, ts)
_poll_count = 0
HISTORY_SAMPLE_EVERY_N_POLLS = 12  # 12 * 5s = 60s


def _compute_mbps(previous: tuple[int, int, datetime], current_tx: int, current_rx: int, now: datetime) -> tuple[float, float]:
    prev_tx, prev_rx, prev_ts = previous
    elapsed = (now - prev_ts).total_seconds()
    if elapsed <= 0:
        return 0.0, 0.0
    tx_mbps = max(0, (current_tx - prev_tx) * 8 / elapsed / 1_000_000)
    rx_mbps = max(0, (current_rx - prev_rx) * 8 / elapsed / 1_000_000)
    return round(tx_mbps, 3), round(rx_mbps, 3)


def poll_interface_stats() -> None:
    """Called every 5 seconds by the scheduler. Fetches current
    interfaces for every onboarded device, computes Mbps against the
    previous sample, and caches the result for the topology graph API.
    Also appends a downsampled history sample every 60s (see module
    docstring) for the real bandwidth-trend chart."""
    global _poll_count
    _poll_count += 1
    record_history = (_poll_count % HISTORY_SAMPLE_EVERY_N_POLLS) == 0

    now = datetime.utcnow()
    for device in store.list_devices():
        try:
            driver = get_driver(device)
            driver.connect()
            interfaces = driver.get_interfaces()
        except Exception:
            continue

        updated: list[Interface] = []
        for iface in interfaces:
            key = (device.device_id, iface.if_name)
            if iface.tx_bytes is not None and iface.rx_bytes is not None:
                previous = _previous_samples.get(key)
                if previous is not None:
                    iface.tx_mbps, iface.rx_mbps = _compute_mbps(previous, iface.tx_bytes, iface.rx_bytes, now)
                _previous_samples[key] = (iface.tx_bytes, iface.rx_bytes, now)
            updated.append(iface)

        store.set_interface_stats(device.device_id, updated)
        check_interface_alarms(device.device_id, updated)
        if record_history:
            store.add_interface_stat_samples(device.device_id, updated)
