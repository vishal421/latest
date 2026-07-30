from datetime import datetime

from app.models import ConfigBackup
from app.store import store


def setup_function():
    store.clear_all_for_tests()


def test_add_and_list_config_backup():
    store.add_config_backup(ConfigBackup(
        device_id="rt-1", taken_at=datetime.utcnow(), status="success",
        size_bytes=1024, content="hostname router-edge-1\n!\nend\n",
    ))
    backups = store.list_config_backups("rt-1")
    assert len(backups) == 1
    assert backups[0].status == "success"
    assert backups[0].size_bytes == 1024
    assert backups[0].content == ""  # list view omits content


def test_get_config_backup_content_by_id():
    created = store.add_config_backup(ConfigBackup(
        device_id="rt-1", taken_at=datetime.utcnow(), status="success",
        size_bytes=20, content="hostname router-edge-1\n",
    ))
    content = store.get_config_backup_content(created.backup_id)
    assert content == "hostname router-edge-1\n"


def test_failed_backup_records_error():
    store.add_config_backup(ConfigBackup(
        device_id="rt-1", taken_at=datetime.utcnow(), status="failed",
        error="connection timed out",
    ))
    backups = store.list_config_backups("rt-1")
    assert backups[0].status == "failed"
    assert backups[0].error == "connection timed out"


def test_backups_accumulate_not_overwrite():
    store.add_config_backup(ConfigBackup(device_id="rt-1", taken_at=datetime.utcnow(), status="success", content="v1"))
    store.add_config_backup(ConfigBackup(device_id="rt-1", taken_at=datetime.utcnow(), status="success", content="v2"))
    assert len(store.list_config_backups("rt-1")) == 2
