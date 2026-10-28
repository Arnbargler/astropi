"""Read-only status: never opens the camera or issues mount commands."""
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess

from .config import Settings

def usb_present(vendor: str, product: str, root: Path) -> bool:
    try:
        for entry in root.iterdir():
            try:
                vid = (entry / "idVendor").read_text().strip().lower()
                pid = (entry / "idProduct").read_text().strip().lower()
            except OSError:
                continue
            if (vid, pid) == (vendor.lower(), product.lower()):
                return True
    except OSError:
        pass
    return False

def mounted_uuid(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["findmnt", "--mountpoint", str(path), "--noheadings", "--output", "UUID"],
            capture_output=True, text=True, timeout=2, check=True
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

def storage_status(path: Path, expected_uuid: str, *, is_mount=os.path.ismount, uuid_lookup=mounted_uuid) -> dict:
    result = dict(mount=str(path), mounted=False, uuid_match=False,
                  writable=False, ready=False, free_bytes=None, state="missing")
    if not path.is_dir():
        return result
    if not is_mount(path):
        result["state"] = "not_mounted"
        return result
    result["mounted"] = True
    uuid = uuid_lookup(path)
    if not uuid or uuid.lower() != expected_uuid.lower():
        result["state"] = "wrong_or_unknown_uuid"
        return result
    result["uuid_match"] = True
    result["writable"] = os.access(path, os.W_OK)
    try:
        stat = os.statvfs(path)
        result["free_bytes"] = stat.f_bavail * stat.f_frsize
    except OSError:
        result["state"] = "stat_error"
        return result
    result["ready"] = result["writable"]
    result["state"] = "ready" if result["ready"] else "not_writable"
    return result

def cpu_temperature() -> float | None:
    try:
        return round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()) / 1000, 1)
    except (OSError, ValueError):
        return None

def uptime() -> int | None:
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return None

def snapshot(settings: Settings) -> dict:
    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "camera": {"usb_detected": usb_present("f266", "9a0a", settings.usb_sysfs),
                   "sdk_connected": False},
        "mount": {"usb_detected": usb_present("03c3", "4001", settings.usb_sysfs),
                  "serial_present": settings.mount_serial.exists(), "connected": False},
        "storage": storage_status(settings.storage_mount, settings.storage_uuid),
        "host": {"cpu_temperature_c": cpu_temperature(), "uptime_seconds": uptime()},
    }
