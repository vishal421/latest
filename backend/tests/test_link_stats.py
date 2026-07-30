from unittest.mock import patch, MagicMock

import pytest

from app.models import Device, Vendor, DeviceType, Interface
from app.store import store
import app.link_stats as link_stats


def setup_function():
    store.clear_all_for_tests()
    link_stats._previous_samples.clear()


@patch("app.link_stats.get_driver")
def test_mbps_is_none_on_first_sample(mock_get_driver):
    sw = Device(device_id="sw-1", hostname="sw1", mgmt_ip="10.0.0.5",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    store.add_device(sw)

    mock_driver = MagicMock()
    mock_driver.get_interfaces.return_value = [
        Interface(device_id="sw-1", if_name="Gi0/1", tx_bytes=1000, rx_bytes=2000),
    ]
    mock_get_driver.return_value = mock_driver

    link_stats.poll_interface_stats()

    cached = store.get_interface_stats("sw-1")
    assert cached[0].tx_mbps is None  # no previous sample to diff against yet


@patch("app.link_stats.get_driver")
def test_mbps_computed_from_second_sample(mock_get_driver):
    sw = Device(device_id="sw-1", hostname="sw1", mgmt_ip="10.0.0.5",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    store.add_device(sw)

    mock_driver = MagicMock()
    mock_get_driver.return_value = mock_driver

    # First sample
    mock_driver.get_interfaces.return_value = [
        Interface(device_id="sw-1", if_name="Gi0/1", tx_bytes=0, rx_bytes=0),
    ]
    link_stats.poll_interface_stats()

    # Force the previous sample's timestamp back 5 seconds so the second
    # poll has a real elapsed time to divide by.
    from datetime import datetime, timedelta
    key = ("sw-1", "Gi0/1")
    tx, rx, ts = link_stats._previous_samples[key]
    link_stats._previous_samples[key] = (tx, rx, ts - timedelta(seconds=5))

    # Second sample: 625,000 bytes transferred in 5 seconds = 1 Mbps
    mock_driver.get_interfaces.return_value = [
        Interface(device_id="sw-1", if_name="Gi0/1", tx_bytes=625_000, rx_bytes=1_250_000),
    ]
    link_stats.poll_interface_stats()

    cached = store.get_interface_stats("sw-1")
    assert cached[0].tx_mbps == pytest.approx(1.0, abs=0.01)
    assert cached[0].rx_mbps == pytest.approx(2.0, abs=0.01)


@patch("app.link_stats.get_driver")
def test_history_only_recorded_every_nth_poll(mock_get_driver):
    sw = Device(device_id="sw-1", hostname="sw1", mgmt_ip="10.0.0.5",
                vendor=Vendor.CISCO_IOS, device_type=DeviceType.SWITCH)
    store.add_device(sw)

    mock_driver = MagicMock()
    mock_driver.get_interfaces.return_value = [
        Interface(device_id="sw-1", if_name="Gi0/1", tx_bytes=0, rx_bytes=0),
    ]
    mock_get_driver.return_value = mock_driver

    link_stats._poll_count = 0  # reset for test isolation
    for _ in range(link_stats.HISTORY_SAMPLE_EVERY_N_POLLS - 1):
        link_stats.poll_interface_stats()
    assert store.get_interface_stat_history(device_id="sw-1") == []  # not yet at the Nth poll

    link_stats.poll_interface_stats()  # this is the Nth poll
    assert len(store.get_interface_stat_history(device_id="sw-1")) == 1


@patch("app.link_stats.get_driver")
def test_interfaces_without_counters_left_as_none(mock_get_driver):
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1",
                vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw)

    mock_driver = MagicMock()
    mock_driver.get_interfaces.return_value = [
        Interface(device_id="fw-1", if_name="ethernet1/1"),  # no tx/rx bytes -- PAN-OS TODO
    ]
    mock_get_driver.return_value = mock_driver

    link_stats.poll_interface_stats()

    cached = store.get_interface_stats("fw-1")
    assert cached[0].tx_mbps is None
    assert cached[0].rx_mbps is None
