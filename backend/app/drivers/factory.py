"""
(vendor, device_type) -> driver class registry. This is the ONE place
in the codebase that knows the mapping from vendor+type to
implementation -- adding a new vendor/type means adding one line here
plus the new driver module, and nothing else changes.
"""
from __future__ import annotations

from app.models import Device, Vendor, DeviceType
from app.drivers.base import DeviceDriver
from app.drivers.paloalto import PaloAltoDriver
from app.drivers.fortigate import FortigateDriver
from app.drivers.cisco_ios import CiscoIOSRouterDriver, CiscoIOSSwitchDriver
from app.vault import vault

_REGISTRY = {
    (Vendor.PALOALTO, DeviceType.FIREWALL): PaloAltoDriver,
    (Vendor.FORTIGATE, DeviceType.FIREWALL): FortigateDriver,
    (Vendor.CISCO_IOS, DeviceType.ROUTER): CiscoIOSRouterDriver,
    (Vendor.CISCO_IOS, DeviceType.SWITCH): CiscoIOSSwitchDriver,
}


def get_driver(device: Device) -> DeviceDriver:
    driver_cls = _REGISTRY.get((device.vendor, device.device_type))
    if driver_cls is None:
        raise ValueError(
            f"No driver registered for vendor={device.vendor} device_type={device.device_type}"
        )
    credential = vault.retrieve(device.credential_ref)
    return driver_cls(device, credential)
