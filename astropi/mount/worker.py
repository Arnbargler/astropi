"""One serial-owning AM3N worker: telemetry and *bounded* manual jogs.

Manual movement is opt-in on every jog. Server-enforced heartbeat (600 ms)
and hard-stop commands remain on the serial owner thread, independent of the
browser refresh rate. Unplug/process/power failure CANNOT guarantee a stop;
a physical Cancel/power-disconnect remains mandatory during real tests.
No Home, GoTo, Park, tracking, time/site setters or arbitrary serial commands.
"""
from datetime import datetime, timezone
from pathlib import Path
import re
import threading
import time

import serial

# Intentional hard-coded whitelist. NEVER let a client supply serial commands.
QUERIES = frozenset((":GVP#", ":GV#", ":GU#", ":GA#", ":GZ#", ":GR#", ":GD#"))
# Rate mapping: :R5# and :Rv120.00# were physically verified in earlier
# manual AM3N probes. ZWO AM3N supports 8x/20x/60x sidereal rates; 20x and
# 60x command-specific behaviour still require controlled on-Pi tests.
# NEVER accept a raw serial command or arbitrary speed from a web request.
JOG_COMMANDS = {"north": ":Mn#", "south": ":Ms#", "east": ":Me#", "west": ":Mw#"}
JOG_SPEEDS = {
    "slow": (":R5#", 3.0),          # ~8x, verified on Pi
    "medium": (":Rv20.00#", 2.0),  # 20x, hardware test pending
    "fast": (":Rv60.00#", 1.0),    # 60x, hardware test pending
}
JOG_RATE = JOG_SPEEDS["slow"][0]  # backward-compatible default
STOP_COMMAND = ":Q#"
DEADMAN_SECONDS = 0.6
MAX_JOG_SECONDS = 3.0  # independent cap even when client keeps heartbeating
STILL_TOLERANCE_DEG = 0.0006  # ~2 arcsec

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
    """Recognize known *present* AM3N flags, never assume fixed offsets.

    The real Pi reported nNZM... when H (Home) was absent and nNHZM...
    when H was present. Optional flags shift subsequent characters.
    Only positive observations are decoded; absent flags remain unknown
    except for the explicitly reported "n" / "N" negative-state markers.
    M starts an undocumented suffix, which is still preserved verbatim.
    """
    flags = value.split("M", 1)[0]
    return {
        "tracking": False if "n" in flags else None,
        "slewing": False if "N" in flags else None,
        "at_home": True if "H" in flags else None,
        "altaz_mode": True if "Z" in flags else None,
    }


_TELEMETRY = {
    "raw_status": None, "tracking": None, "slewing": None,
    "at_home": None, "altaz_mode": None,
    "altitude_text": None, "azimuth_text": None, "ra_text": None, "dec_text": None,
    "altitude_deg": None, "azimuth_deg": None, "ra_hours": None, "dec_deg": None,
    "updated_utc": None,
}


class MountWorker:
    def __init__(self, serial_path, *, serial_factory=None, poll_interval=2.0, clock=time.monotonic):
        self.path = Path(serial_path)
        self._factory = serial_factory if serial_factory is not None else serial.Serial
        self._interval = poll_interval
        self._clock = clock
        self._lock = threading.Lock()
        self._armed = False
        self._direction = None
        self._pending_direction = None
        self._pending_speed = "slow"
        self._motion_deadline = 0.0
        self._hard_deadline = 0.0
        self._stop_pending = False
        self._stop_reason = None
        self._ever_moved = False
        self._stop_sent_at = None
        self._stop_attempts = 0
        self._last_axes = None
        self._stable_count = 0
        self._stop = threading.Event()
        self._thread = None
        self._state = {
            "phase": "disconnected", "connected": False,
            "serial_path": str(self.path),
            "model": None, "firmware": None, "last_error": None,
            "motion_phase": "idle", "motion_armed": False,
            "motion_direction": None, "jog_speed": "slow",
            "last_stop_reason": None,
            "last_stop_sent_utc": None, "stop_stable": False,
            "motion_warning": None,
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
            self._armed = False
            self._direction = self._pending_direction = None
            self._pending_speed = "slow"
            self._motion_deadline = 0.0
            self._hard_deadline = 0.0
            self._stop_pending = False
            self._ever_moved = False
            self._stop_sent_at = None
            self._stop_attempts = 0
            self._last_axes = None
            self._stable_count = 0
            self._state.update(
                phase="connecting", connected=False, model=None,
                firmware=None, last_error=None, motion_phase="idle",
                motion_armed=False, motion_direction=None, jog_speed="slow",
                last_stop_reason=None, last_stop_sent_utc=None,
                stop_stable=False, motion_warning=None, **_TELEMETRY
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
            self._armed = False
            self._pending_direction = None
            self._stop.set()
            # On disconnect, the serial-owner's finally block sends :Q#
            # BEFORE closing if any jog or stop has been requested.
            self._state.update(
                phase="disconnecting", connected=False, motion_armed=False,
                motion_phase="disconnecting", **_TELEMETRY
            )
            return True

    def arm(self):
        """Requires operator lease at the Flask layer; one arm per jog."""
        with self._lock:
            if not self._state["connected"] or self._state["phase"] != "connected":
                raise RuntimeError("Connect the mount before arming")
            if self._state["motion_phase"] != "idle" or self._stop_pending:
                raise RuntimeError("Mount must be idle and stable before arming")
            self._armed = True
            self._state["motion_armed"] = True
            return True

    def jog(self, direction, speed="slow"):
        if type(direction) is not str or direction not in JOG_COMMANDS:
            raise ValueError("Unknown mount direction")
        if type(speed) is not str or speed not in JOG_SPEEDS:
            raise ValueError("Unknown mount jog speed; select slow, medium or fast")
        with self._lock:
            if not self._state["connected"] or not self._armed:
                raise RuntimeError("Enable manual movement first")
            if self._state["motion_phase"] != "idle":
                raise RuntimeError("Only one direction at a time")
            if self._stop_pending or self._stop.is_set():
                raise RuntimeError("A Stop or disconnect is pending")
            self._pending_direction = direction
            self._pending_speed = speed
            self._motion_deadline = self._clock() + DEADMAN_SECONDS
            self._hard_deadline = self._clock() + min(
                MAX_JOG_SECONDS, JOG_SPEEDS[speed][1]
            )
            self._state.update(motion_phase="starting",
                               motion_direction=direction, jog_speed=speed)
            return direction

    def heartbeat(self, direction):
        with self._lock:
            if (direction != self._direction and direction != self._pending_direction) or not self._armed:
                raise RuntimeError("No matching active manual jog")
            if self._state["motion_phase"] not in ("starting", "moving"):
                raise RuntimeError("No active manual jog")
            # A delayed keepalive cannot revive an expired jog.
            if self._clock() >= self._hard_deadline:
                self._queue_stop_locked("Maximum jog duration reached")
                raise RuntimeError("Jog speed time limit reached; Stop requested")
            if self._clock() >= self._motion_deadline:
                self._queue_stop_locked("Deadman heartbeat expired")
                raise RuntimeError("Manual jog expired and Stop was requested")
            self._motion_deadline = self._clock() + DEADMAN_SECONDS
            return True

    def _queue_stop_locked(self, reason):
        self._armed = False
        self._pending_direction = None
        self._motion_deadline = 0.0
        self._hard_deadline = 0.0
        self._stop_pending = True
        self._stop_reason = reason
        self._state.update(
            motion_armed=False, motion_phase="stopping",
            last_stop_reason=reason, stop_stable=False, motion_warning=None
        )

    def emergency_stop(self, reason="Emergency Stop requested"):
        """Available even to viewers. Request is NOT confirmation of halt."""
        with self._lock:
            if self._state["phase"] != "connected" or not self._state["connected"]:
                raise RuntimeError("Mount serial port is not connected; use physical Stop")
            self._queue_stop_locked(reason)
            return True

    def _write_motion(self, port, command):
        if command not in (
            STOP_COMMAND, *JOG_COMMANDS.values(),
            *(rate for rate, _ in JOG_SPEEDS.values())
        ):
            raise MountProtocolError("Refusing non-whitelisted motion command")
        port.write(command.encode("ascii"))
        port.flush()

    def _service_motion(self, port):
        """Serial-owner only. Hold the state lock across a jog command.

        This prevents an HTTP Stop from racing between selecting a direction
        and actually sending :M?#. Stop cannot be overtaken by a stale start.
        """
        now = self._clock()
        with self._lock:
            if self._state["motion_phase"] in ("starting", "moving"):
                if now >= self._hard_deadline:
                    self._queue_stop_locked("Maximum jog duration reached")
                elif now >= self._motion_deadline:
                    self._queue_stop_locked("Deadman heartbeat expired")
            if self._stop_pending:
                self._stop_pending = False
                self._pending_direction = None
                self._direction = None
                self._armed = False
                self._state.update(motion_armed=False, motion_direction=None)
                # If this write fails, the finally-block retries a Stop.
                self._write_motion(port, STOP_COMMAND)
                self._stop_sent_at = self._clock()
                self._last_axes = None
                self._stable_count = 0
                self._stop_attempts += 1
                self._state["last_stop_sent_utc"] = datetime.now(timezone.utc).isoformat()
                self._state["motion_phase"] = "stopping"
            elif self._pending_direction is not None:
                direction = self._pending_direction
                speed = self._pending_speed
                self._pending_direction = None
                self._direction = direction
                self._ever_moved = True  # ensure a finally-block Stop attempt
                # Always establish the proven slow R5 baseline first. If an
                # experimental :Rvxx.xx# rate is ignored, the mount should
                # remain at the verified 8x rate, not inherit an unknown HC rate.
                self._write_motion(port, JOG_RATE)
                if speed != "slow":
                    self._write_motion(port, JOG_SPEEDS[speed][0])
                self._write_motion(port, JOG_COMMANDS[direction])
                self._state["motion_phase"] = "moving"

    def _check_stopped(self, altitude, azimuth):
        with self._lock:
            if self._state["motion_phase"] != "stopping" or self._stop_sent_at is None:
                return
            now = self._clock()
            if self._last_axes is not None:
                last_alt, last_az = self._last_axes
                # Shortest azimuth arc handles 359.999 -> 0.001 wrap.
                az_difference = abs((azimuth - last_az + 180) % 360 - 180)
                if abs(altitude - last_alt) < STILL_TOLERANCE_DEG and az_difference < STILL_TOLERANCE_DEG:
                    self._stable_count += 1
                else:
                    self._stable_count = 0
            self._last_axes = (altitude, azimuth)
            if self._stable_count >= 2 and now - self._stop_sent_at >= 1.2:
                self._state.update(motion_phase="idle", stop_stable=True,
                                   motion_direction=None)
                self._direction = None
                self._ever_moved = False
            elif now - self._stop_sent_at >= 3:
                if self._stop_attempts < 3:
                    self._stop_pending = True  # retry :Q# then recheck axes
                else:
                    self._state.update(
                        motion_phase="uncertain", motion_warning=
                        "Reported axes have not stabilized. Use the mount's PHYSICAL Stop/power cutoff."
                    )
                    # Remain disarmed and do not accept another jog.

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
        # Check emergency stop and heartbeat watchdog between *every* serial
        # query. Serial reads have a 0.35s upper bound, so Stop is prioritized.
        replies = []
        for cmd in (":GU#", ":GA#", ":GZ#", ":GR#", ":GD#"):
            self._service_motion(port)
            replies.append(self._query(port, cmd))
        raw, altitude, azimuth, ra, dec = replies
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
        self._check_stopped(parsed["altitude_deg"], parsed["azimuth_deg"])

    def _run(self):
        port = None
        problem = None
        try:
            if not self.path.exists():
                raise FileNotFoundError(f"Mount serial alias missing: {self.path}")
            port = self._factory(
                port=str(self.path), baudrate=9600, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                timeout=0.35, write_timeout=0.35,
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
            last_poll = -float("inf")
            while not self._stop.is_set():
                self._service_motion(port)
                now = self._clock()
                with self._lock:
                    phase = self._state["motion_phase"]
                interval = min(self._interval, 0.35) if phase in ("moving", "starting", "stopping") else self._interval
                if now - last_poll >= interval:
                    self._poll(port)
                    last_poll = self._clock()
                self._stop.wait(0.05)
        except InterruptedError:
            pass  # User-requested disconnect, no failure.
        except (OSError, serial.SerialException, MountProtocolError, ValueError) as exc:
            if not self._stop.is_set():
                problem = str(exc)
        except Exception as exc:
            if not self._stop.is_set():
                problem = f"Mount read-only polling failed: {exc}"
        finally:
            # Best effort only. If serial is physically lost, Python dies, or
            # the motor controller is unresponsive, physical Stop is mandatory.
            with self._lock:
                needs_stop = (self._ever_moved or self._stop_pending or
                              self._state["motion_phase"] in ("moving","starting","stopping"))
                self._armed = False
                self._pending_direction = self._direction = None
            if port is not None:
                if needs_stop:
                    try:
                        self._write_motion(port, STOP_COMMAND)
                    except Exception as exc:
                        problem = (problem or "Mount Stop not confirmed") + (
                            f"; final physical Stop required ({exc})"
                        )
                try:
                    port.close()
                except (OSError, serial.SerialException):
                    pass
            with self._lock:
                self._state.update(
                    phase="error" if problem else "disconnected",
                    connected=False, last_error=problem, motion_armed=False,
                    motion_direction=None, motion_phase="idle",
                    stop_stable=False, **_TELEMETRY,
                )
