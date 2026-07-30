"""
Periodic polling: health snapshots + log ingestion for every onboarded
device. Uses APScheduler for the MVP -- swap for Celery+Redis if you
need multi-worker/distributed polling later.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.drivers.factory import get_driver
from app.store import store
from app.link_stats import poll_interface_stats
from app.alerting import check_health_alarms
from app.drivers.base import DriverNotSupported

logger = logging.getLogger("infraos.scheduler")

HEALTH_POLL_INTERVAL_SECONDS = 60
LOG_POLL_INTERVAL_SECONDS = 120
INTERFACE_STATS_POLL_INTERVAL_SECONDS = 5
LICENSE_POLL_INTERVAL_SECONDS = 6 * 60 * 60  # licenses rarely change -- no need to hammer the device
CONFIG_BACKUP_INTERVAL_SECONDS = 24 * 60 * 60  # daily backup, same cadence real NCM tools use
SESSION_POLL_INTERVAL_SECONDS = 120  # same cadence as log polling
SESSION_RETENTION_MINUTES = 60  # longer than the 30-min log retention -- session history is what Troubleshooting correlates against


def poll_all_health() -> None:
    for device in store.list_devices():
        try:
            driver = get_driver(device)
            driver.connect()
            snapshot = driver.health_check()
            store.add_health_snapshot(snapshot)
            check_health_alarms(device.device_id, snapshot)
        except Exception as exc:  # noqa: BLE001 -- polling must never crash the loop
            logger.warning("health poll failed for %s: %s", device.device_id, exc)


def poll_all_config_backups() -> None:
    from app.models import ConfigBackup
    from app.config_pipeline import parse_and_store
    for device in store.list_devices():
        try:
            driver = get_driver(device)
            driver.connect()
            content = driver.get_running_config()
            backup = store.add_config_backup(ConfigBackup(
                device_id=device.device_id, taken_at=datetime.utcnow(),
                status="success", size_bytes=len(content.encode()), content=content,
            ))
            parse_and_store(device, backup)
        except DriverNotSupported:
            pass  # this device type doesn't have a config-backup concept
        except Exception as exc:  # noqa: BLE001
            logger.warning("config backup failed for %s: %s", device.device_id, exc)
            store.add_config_backup(ConfigBackup(
                device_id=device.device_id, taken_at=datetime.utcnow(),
                status="failed", error=str(exc),
            ))


def poll_all_licenses() -> None:
    for device in store.list_devices():
        try:
            driver = get_driver(device)
            driver.connect()
            licenses = driver.get_licenses()
            store.set_licenses(device.device_id, licenses)
        except DriverNotSupported:
            pass  # this vendor/device type doesn't expose license data yet -- not an error
        except Exception as exc:  # noqa: BLE001
            logger.warning("license poll failed for %s: %s", device.device_id, exc)


LOG_TYPES_TO_POLL = ("traffic", "threat", "url", "system")


def poll_all_logs() -> None:
    since = datetime.utcnow() - timedelta(seconds=LOG_POLL_INTERVAL_SECONDS * 2)
    for device in store.list_devices():
        driver = None
        for log_type in LOG_TYPES_TO_POLL:
            try:
                if driver is None:
                    driver = get_driver(device)
                    driver.connect()
                events = driver.get_logs({"log_type": log_type}, (since, datetime.utcnow()))
                store.add_logs(events)
            except Exception as exc:  # noqa: BLE001
                logger.warning("log poll (%s) failed for %s: %s", log_type, device.device_id, exc)


def poll_all_sessions() -> None:
    """Snapshot each firewall's live session table into SessionSnapshotRow
    so Troubleshooting has real history to correlate against, not just
    whatever happens to be live at the exact moment a trace runs.
    Routers aren't polled here -- their flow tables are typically much
    larger/more ephemeral, and Troubleshooting already queries them
    live for the router-log step."""
    from app.models import DeviceType
    for device in store.list_devices():
        if device.device_type != DeviceType.FIREWALL:
            continue
        try:
            driver = get_driver(device)
            driver.connect()
            sessions = driver.get_sessions()
            store.add_sessions(device.device_id, sessions)
        except DriverNotSupported:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("session poll failed for %s: %s", device.device_id, exc)


def cleanup_old_sessions() -> None:
    store.cleanup_old_sessions(datetime.utcnow() - timedelta(minutes=SESSION_RETENTION_MINUTES))


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(poll_all_health, "interval", seconds=HEALTH_POLL_INTERVAL_SECONDS, id="health_poll")
    scheduler.add_job(poll_all_logs, "interval", seconds=LOG_POLL_INTERVAL_SECONDS, id="log_poll")
    scheduler.add_job(poll_interface_stats, "interval", seconds=INTERFACE_STATS_POLL_INTERVAL_SECONDS, id="interface_stats_poll")
    scheduler.add_job(poll_all_licenses, "interval", seconds=LICENSE_POLL_INTERVAL_SECONDS, id="license_poll")
    scheduler.add_job(poll_all_config_backups, "interval", seconds=CONFIG_BACKUP_INTERVAL_SECONDS, id="config_backup_poll")
    scheduler.add_job(poll_all_sessions, "interval", seconds=SESSION_POLL_INTERVAL_SECONDS, id="session_poll")
    scheduler.add_job(cleanup_old_sessions, "interval", seconds=SESSION_POLL_INTERVAL_SECONDS, id="session_cleanup")
    scheduler.start()
    return scheduler
