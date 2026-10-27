"""Explicitly connected, READ-ONLY ZWO AM3N telemetry worker.

Only this thread owns the 9600 8N1 serial handle; Flask only reads its cached
status. No implicit mount connection at service startup. There are no movement,
Home, Park, time/site, slew-rate or tracking setters in this module or API.
USB disappearance/errors close the port and clear potentially stale pointing
values; an operator must explicitly reconnect.
"""
from datetime import datetime, timezone
from pathlib import Path
import re
import threading

import serial

# Intentional hard-coded whitelist. NEVER let a client supply serial commands.
QUERIES = frozenset((":GVP#", ":GV#", ":GU#", ":GA#", ":GZ#", ":GR#", ":GD#"))
_ANGLE = re.compile(r"^([+-]?)(\d{1,3})\*(\d{2}):(\d{2}(?:\.\d+)?)$")
_CLOCK = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$")


class MountProtocolError(RuntimeError):
    pass


def angle_degrees(value, *, signed=False, limit=90):
    """Parse AM3N DDD*MM:SS, validating ranges, without normalizing signs."""
    match = _ANGLE.fullmatch(value)
    if not match:
        raise MountProtocolError(f"Invalid mount angle: {value!r}")
    sign, whole, minutes, seconds = match.groups()
    d, m, s = int(whole), int(minutes), float(seconds)
    if (signed and sign not in ("+", "-")) or m >= 60 or s >= 60 or d > limit:
        raise MountProtocolError(f"Out-of-range mount angle: {value!r}")
    if d == limit and (m or s):
        raise MountProtocolError(f"Out-of-range mount angle: {value!r}")
    return round((-1 if sign == "-" else 1) * (d + m / 60 + s / 3600), 6)


def ra_hours(value):
    match = _CLOCK.fullmatch(value)
    if not match:
        raise MountProtocolError(f"Invalid mount RA: {value!r}")
    hours, minutes, seconds = int(match[1]), int(match[2]), float(match[3])
    if hours > 24 or minutes >= 60 or seconds >= 60 or (hours == 24 and (minutes or seconds)):
        raise MountProtocolError(f"Out-of-range mount RA: {value!r}")
    return round(hours + minutes / 60 + seconds / 3600, 7)


def known_flags(value):
    """Only interpret flag positions confirmed for this specific mount.

    Unknown flags are None, not assumed motion/accuracy information. :GU#
    has an undocumented suffix; always preserve it verbatim for diagnosis.
    """
    return {
        "tracking": False if value[:1] == "n" else None,
        "slewing": False if value[1:2] == "N" else None,
        "at_home": True if value[2:3] == "H" else None,
        "altaz_mode": True if value[3:4] == "Z" else None,
    }


_TELEMETRY = {
    "raw_status": None, "tracking": None, "slewing": None,
    "at_home": None, "altaz_mode": None,
    "altitude_text": None, "azimuth_text": None, "ra_text": None, "dec_text": None,
    "altitude_deg": None, "azimuth_deg": None, "ra_hours": None, "dec_deg": None,
    "updated_utc": None,
}


class MountWorker:
    def __init__(self, serial_path, *, serial_factory=None, poll_interval=2.0):
        self.path = Path(serial_path)
        self._factory = serial_factory if serial_factory is not None else serial.Serial
        self._interval = poll_interval
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._state = {
            "phase": "disconnected", "connected": False,
            "serial_path": str(self.path),
            "model": None, "firmware": None, "last_error": None,
            **_TELEMETRY,
        }

    def status(self):
        with self._lock:
            return dict(self._state)

    def connect(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop = threading.Event()
            self._state.update(
                phase="connecting", connected=False, model=None,
                firmware=None, last_error=None, **_TELEMETRY
            )
            self._thread = threading.Thread(
                target=self._run, name="am3n-readonly", daemon=True
            )
            self._thread.start()
            return True

    def disconnect(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return False
            self._stop.set()
            self._state.update(phase="disconnecting", connected=False, **_TELEMETRY)
            return True

    def _query(self, port, command):
        if command not in QUERIES:
            raise MountProtocolError("Refusing non-read-only mount command")
        if self._stop.is_set():
            raise InterruptedError("Mount disconnect requested")
        port.write(command.encode("ascii"))
        port.flush()
        data = port.read_until(b"#", size=96)
        if not data.endswith(b"#") or len(data) < 2:
            raise MountProtocolError(f"No complete mount response to {command}")
        try:
            response = data[:-1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise MountProtocolError("Mount response not ASCII") from exc
        if not response or any(ord(c) < 32 or ord(c) > 126 for c in response):
            raise MountProtocolError(f"Invalid mount response to {command}")
        return response

    def _poll(self, port):
        # The mount reports positions whether or not it is aligned. They MUST
        # be labeled as *reported*, not proven true celestial pointing.
        raw = self._query(port, ":GU#")
        altitude = self._query(port, ":GA#")
        azimuth = self._query(port, ":GZ#")
        ra = self._query(port, ":GR#")
        dec = self._query(port, ":GD#")
        parsed = {
            "raw_status": raw, **known_flags(raw),
            "altitude_text": altitude, "azimuth_text": azimuth,
            "ra_text": ra, "dec_text": dec,
            "altitude_deg": angle_degrees(altitude, signed=True, limit=90),
            "azimuth_deg": angle_degrees(azimuth, limit=360),
            "ra_hours": ra_hours(ra),
            "dec_deg": angle_degrees(dec, signed=True, limit=90),
            "updated_utc": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            if not self._stop.is_set():
                self._state.update(parsed, phase="connected", connected=True)

    def _run(self):
        port = None
        problem = None
        try:
            if not self.path.exists():
                raise FileNotFoundError(f"Mount serial alias missing: {self.path}")
            port = self._factory(
                port=str(self.path), baudrate=9600, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                timeout=1.0, write_timeout=1.0,
                xonxoff=False, rtscts=False, dsrdtr=False,
            )
            model = self._query(port, ":GVP#")
            if model.strip().upper() != "AM3N":
                raise MountProtocolError(f"Unexpected mount model: {model!r}")
            firmware = self._query(port, ":GV#")
            if not firmware:
                raise MountProtocolError("Empty mount firmware")
            with self._lock:
                self._state.update(model=model, firmware=firmware)
            while not self._stop.is_set():
                self._poll(port)
                self._stop.wait(self._interval)
        except InterruptedError:
            pass  # User-requested disconnect, no failure.
        except (OSError, serial.SerialException, MountProtocolError, ValueError) as exc:
            if not self._stop.is_set():
                problem = str(exc)
        except Exception as exc:
            if not self._stop.is_set():
                problem = f"Mount read-only polling failed: {exc}"
        finally:
            if port is not None:
                try:
                    port.close()
                except (OSError, serial.SerialException):
                    pass
            with self._lock:
                self._state.update(
                    phase="error" if problem else "disconnected",
                    connected=False, last_error=problem, **_TELEMETRY,
                )
