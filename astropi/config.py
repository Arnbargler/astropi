"""Paths for the verified AstroPi hardware; overridable for testing."""
import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    storage_mount: Path
    storage_uuid: str
    mount_serial: Path
    usb_sysfs: Path

    @classmethod
    def from_environment(cls):
        return cls(
            storage_mount=Path(os.getenv("ASTROPI_STORAGE_MOUNT", "/media/astropi-data")),
            storage_uuid=os.getenv("ASTROPI_STORAGE_UUID", "25b33cfa-b178-4b86-8a15-d00c8305cca5"),
            mount_serial=Path(os.getenv("ASTROPI_MOUNT_SERIAL", "/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00")),
            usb_sysfs=Path(os.getenv("ASTROPI_USB_SYSFS", "/sys/bus/usb/devices")),
        )
