from datetime import datetime, timedelta

from app.models import Interface
from app.store import store


def setup_function():
    store.clear_all_for_tests()


def test_add_and_get_interface_stat_history():
    store.add_interface_stat_samples("sw-1", [
        Interface(device_id="sw-1", if_name="Gi0/1", tx_mbps=10.5, rx_mbps=20.1, oper_status="up"),
        Interface(device_id="sw-1", if_name="Gi0/2", tx_mbps=None, rx_mbps=None, oper_status="down"),
    ])
    history = store.get_interface_stat_history(device_id="sw-1")
    # only Gi0/1 has an actual reading -- Gi0/2 (no mbps data) shouldn't
    # be recorded, there's nothing real to chart for it
    assert len(history) == 1
    assert history[0]["if_name"] == "Gi0/1"
    assert history[0]["tx_mbps"] == 10.5


def test_history_accumulates_across_multiple_polls():
    store.add_interface_stat_samples("sw-1", [Interface(device_id="sw-1", if_name="Gi0/1", tx_mbps=5, rx_mbps=5)])
    store.add_interface_stat_samples("sw-1", [Interface(device_id="sw-1", if_name="Gi0/1", tx_mbps=8, rx_mbps=9)])
    history = store.get_interface_stat_history(device_id="sw-1", if_name="Gi0/1")
    assert len(history) == 2
    assert [h["tx_mbps"] for h in history] == [5, 8]


def test_history_filters_by_since():
    store.add_interface_stat_samples("sw-1", [Interface(device_id="sw-1", if_name="Gi0/1", tx_mbps=5, rx_mbps=5)])
    future_cutoff = datetime.utcnow() + timedelta(minutes=5)
    history = store.get_interface_stat_history(device_id="sw-1", since=future_cutoff)
    assert history == []
