"""One serial-owning AM3N worker: telemetry, manual jogs and verified UTC sync.

Each explicit serial Connect automatically sets the mount clock from the Pi
ONLY after systemd reports NTP synchronization, and verifies date/time from
mount readback. No site changes, Home, Park, tracking, manual time entry or arbitrary
serial commands. Catalogue-only GoTo is operator-triggered;
manual jogging retains its 600ms lost-heartbeat Stop.
"""
from datetime import datetime, timezone
import subprocess
from pathlib import Path
import re
import threading
from .goto import target_of_date, goto_commands, angular_error_deg
import time

import serial

# Intentional hard-coded whitelist. NEVER let a client supply serial commands.
ENVIRONMENT_QUERIES = {
    "utc_offset": ":GG#",
    "date": ":GC#",
    "local_time": ":GL#",
    "latitude": ":Gt#",
    "longitude_west": ":Gg#",
    "sidereal_time": ":GS#",
}
QUERIES = frozenset((
    ":GVP#", ":GV#", ":GU#", ":GA#", ":GZ#", ":GR#", ":GD#",
    *ENVIRONMENT_QUERIES.values()
))
# Fixed AM3N rate whitelist. Never accept raw serial commands or arbitrary
# browser-supplied speed strings.
JOG_COMMANDS = {"north": ":Mn#", "south": ":Ms#", "east": ":Me#", "west": ":Mw#"}
JOG_SPEEDS = {
    "slow": ":R5#",          # ~8x, verified on Pi
    "medium": ":Rv20.00#",  # ~20x, user-reported normal operation
    "fast": ":Rv60.00#",    # ~60x, user-reported normal operation
    "slew": ":R8#",        # 720x, INDI AM driver documented preset
    "max": ":R9#",         # 1440x, INDI AM driver documented preset
}
JOG_RATE = JOG_SPEEDS["slow"]  # backward-compatible default
STOP_COMMAND = ":Q#"
DEADMAN_SECONDS = 0.6
STILL_TOLERANCE_DEG = 0.0006  # ~2 arcsec
CLOCK_VERIFY_TOLERANCE_SECONDS = 6
GOTO_TIMEOUT_SECONDS = 300
_CLOCK_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{2})$")
_CLOCK_TIME = re.compile(r"^(\d{2}):(\d{2}):(\d{2})$")

_ANGLE = re.compile(r"^([+-]?)(\d{1,3})\*(\d{2}):(\d{2}(?:\.\d+)?)$")
_CLOCK = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$")


class MountProtocolError(RuntimeError):
    pass


class ClockSyncError(RuntimeError):
    """Automatic mount UTC synchronization was not verified."""


def system_ntp_synchronized():
    """Trust the Pi clock only once systemd reports an actual NTP sync.

    We do not merely check NTP service enablement or assume that internet
    access means the Pi clock was corrected after a cold boot.
    """
    try:
        result = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        return result.returncode == 0 and result.stdout.strip().lower() == "yes"
    except (OSError, subprocess.TimeoutExpired):
        return False


def parse_mount_utc(date_text, time_text):
    """Strict AM3N MM/DD/YY + HH:MM:SS, with year 20YY (not 19YY)."""
    date_match = _CLOCK_DATE.fullmatch(date_text)
    time_match = _CLOCK_TIME.fullmatch(time_text)
    if not date_match or not time_match:
        raise ClockSyncError("Mount returned invalid clock date/time format")
    month, day, year = (int(v) for v in date_match.groups())
    hour, minute, second = (int(v) for v in time_match.groups())
    try:
        return datetime(2000 + year, month, day, hour, minute, second,
                        tzinfo=timezone.utc)
    except ValueError as exc:
        raise ClockSyncError("Mount returned invalid calendar date/time") from exc


def utc_sync_commands(moment):
    """Use the AM3N-verified UTC-offset, date, then time command sequence."""
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise ClockSyncError("Pi clock must provide a timezone-aware UTC time")
    utc = moment.astimezone(timezone.utc)
    if utc.year < 2025 or utc.year > 2099:
        raise ClockSyncError("Pi clock year is implausible; refusing mount update")
    return (
        ":SG+00:00#",
        f":SC{utc.month:02d}/{utc.day:02d}/{utc.year % 100:02d}#",
        f":SL{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}#",
    )


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
    def __init__(self, serial_path, *, serial_factory=None, poll_interval=2.0,
                 clock=time.monotonic, ntp_checker=None, utc_clock=None):
        self.path = Path(serial_path)
        self._factory = serial_factory if serial_factory is not None else serial.Serial
        self._interval = poll_interval
        self._clock = clock
        self._ntp_checker = ntp_checker if ntp_checker is not None else system_ntp_synchronized
        self._utc_clock = utc_clock if utc_clock is not None else (
            lambda: datetime.now(timezone.utc)
        )
        self._lock = threading.Lock()
        self._armed = False
        self._direction = None
        self._pending_direction = None
        self._pending_speed = "slow"
        self._motion_deadline = 0.0
        self._stop_pending = False
        self._environment_pending = False
        self._environment_in_progress = False
        self._ever_moved = False
        self._stop_sent_at = None
        self._stop_attempts = 0
        self._goto_pending = None
        self._goto_coords = None
        self._goto_started_at = None
        self._goto_stable_count = 0
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
            "environment_phase": "idle",
            "environment_updated_utc": None,
            "environment_error": None,
            "environment": None,
            "time_sync_phase": "idle", "time_sync_error": None,
            "time_sync_verified_utc": None, "time_sync_source": "Pi NTP (UTC)",
            "goto_phase": "idle", "goto_target": None, "goto_error": None,
            "goto_requested_utc": None, "goto_position_error_deg": None,
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
            self._stop_pending = False
            self._environment_pending = False
            self._environment_in_progress = False
            self._ever_moved = False
            self._stop_sent_at = None
            self._stop_attempts = 0
            self._goto_pending = None
            self._goto_coords = None
            self._goto_started_at = None
            self._goto_stable_count = 0
            self._last_axes = None
            self._stable_count = 0
            self._state.update(
                phase="connecting", connected=False, model=None,
                firmware=None, last_error=None, motion_phase="idle",
                motion_armed=False, motion_direction=None, jog_speed="slow",
                last_stop_reason=None, last_stop_sent_utc=None,
                stop_stable=False, motion_warning=None,
                environment_phase="idle", environment_updated_utc=None,
                environment_error=None, environment=None,
                time_sync_phase="checking", time_sync_error=None,
                time_sync_verified_utc=None, goto_phase="idle",
                goto_target=None, goto_error=None, goto_requested_utc=None,
                goto_position_error_deg=None, **_TELEMETRY
            )
            self._thread = threading.Thread(
                target=self._run, name="am3n-serial", daemon=True
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

    def jog(self, direction, speed="slow"):
        if type(direction) is not str or direction not in JOG_COMMANDS:
            raise ValueError("Unknown mount direction")
        if type(speed) is not str or speed not in JOG_SPEEDS:
            raise ValueError("Unknown mount jog speed")
        with self._lock:
            if not self._state["connected"] or self._state["phase"] != "connected":
                raise RuntimeError("Connect the mount before moving")
            if self._state["motion_phase"] != "idle":
                raise RuntimeError("Only one direction at a time")
            if (self._stop_pending or self._stop.is_set() or
                    self._environment_pending or self._environment_in_progress):
                raise RuntimeError("Stop, disconnect or clock/site read pending")
            # Internal motion token: only a valid active jog may renew
            # its heartbeat. No separate browser-side arm action.
            self._armed = True
            self._state["motion_armed"] = True
            self._pending_direction = direction
            self._pending_speed = speed
            self._motion_deadline = self._clock() + DEADMAN_SECONDS
            self._state.update(motion_phase="starting",
                               motion_direction=direction, jog_speed=speed)
            return direction

    def goto(self, target):
        """Queue only a validated Messier catalogue target; no raw coordinates."""
        if not isinstance(target, str) or not re.fullmatch(
            r"M(?:[1-9]|[1-9][0-9]|10[0-9]|110)", target
        ):
            raise ValueError("GoTo requires M1–M110 selected in Find")
        ra, dec = target_of_date(target, self._utc_clock())
        goto_commands(ra, dec)
        with self._lock:
            if not self._state["connected"] or self._state["phase"] != "connected":
                raise RuntimeError("Connect the AM3N before GoTo")
            if self._state["time_sync_phase"] != "verified":
                raise RuntimeError("Verified Pi NTP → mount clock required before GoTo")
            if (self._state["motion_phase"] != "idle" or self._stop_pending or
                self._stop.is_set() or self._environment_pending or
                self._environment_in_progress):
                raise RuntimeError("Mount must be idle before GoTo")
            self._goto_pending = (target, ra, dec)
            self._goto_coords = (ra, dec)
            self._goto_stable_count = 0
            self._state.update(goto_phase="queued", goto_target=target,
                goto_error=None, goto_position_error_deg=None,
                goto_requested_utc=self._utc_clock().isoformat(),
                motion_phase="goto_queued", stop_stable=False)
            return target

    def heartbeat(self, direction):
        with self._lock:
            if (direction != self._direction and direction != self._pending_direction) or not self._armed:
                raise RuntimeError("No matching active manual jog")
            if self._state["motion_phase"] not in ("starting", "moving"):
                raise RuntimeError("No active manual jog")
            # A delayed keepalive cannot revive an expired jog.
            if self._clock() >= self._motion_deadline:
                self._queue_stop_locked("Deadman heartbeat expired")
                raise RuntimeError("Manual jog expired and Stop was requested")
            self._motion_deadline = self._clock() + DEADMAN_SECONDS
            return True

    def _queue_stop_locked(self, reason):
        self._armed = False
        self._pending_direction = None
        self._motion_deadline = 0.0
        self._stop_pending = True
        self._goto_pending = None
        if self._state["goto_phase"] in ("queued", "sending", "slewing"):
            self._state["goto_phase"] = "aborted"
        self._state.update(
            motion_armed=False, motion_phase="stopping",
            last_stop_reason=reason, stop_stable=False, motion_warning=None
        )

    def request_environment_read(self):
        """Queue six read-only AM3N queries; no time/site setter commands."""
        with self._lock:
            if not self._state["connected"] or self._stop.is_set():
                raise RuntimeError("Connect the mount to read its stored clock/site")
            if (self._armed or self._state["motion_phase"] != "idle" or
                    self._environment_pending or self._environment_in_progress):
                raise RuntimeError("Mount must be idle and not already reading clock/site")
            self._environment_pending = True
            self._state.update(environment_phase="queued", environment_error=None)
            return True

    def _service_environment(self, port):
        """Called only by the serial-owner thread when no jog is active."""
        with self._lock:
            if not self._environment_pending or self._state["motion_phase"] != "idle":
                return
            self._environment_pending = False
            self._environment_in_progress = True
            self._state["environment_phase"] = "reading"
        try:
            values = {}
            for key, command in ENVIRONMENT_QUERIES.items():
                self._service_motion(port)  # honor Stop before each request
                values[key] = self._query(port, command)
            with self._lock:
                if not self._stop.is_set():
                    self._state.update(
                        environment=values, environment_phase="ready",
                        environment_updated_utc=datetime.now(timezone.utc).isoformat(),
                        environment_error=None,
                    )
        except (MountProtocolError, OSError, serial.SerialException) as exc:
            with self._lock:
                self._state.update(environment_phase="error",
                                   environment_error=str(exc), environment=None)
        finally:
            with self._lock:
                self._environment_in_progress = False

    def emergency_stop(self, reason="Emergency Stop requested"):
        """Available even to viewers. Request is NOT confirmation of halt."""
        with self._lock:
            if self._state["phase"] != "connected" or not self._state["connected"]:
                raise RuntimeError("Mount serial port is not connected; use physical Stop")
            self._queue_stop_locked(reason)
            return True

    def _write_goto(self, port, command, expected):
        """Only internally generated, whitelisted :Sr/:Sd/:MS protocol."""
        if not (re.fullmatch(r":Sr\d{2}:\d{2}:\d{2}#", command) or
                re.fullmatch(r":Sd[+-]\d{2}\*\d{2}:\d{2}#", command) or
                command == ":MS#"):
            raise MountProtocolError("Refusing unapproved GoTo command")
        port.write(command.encode("ascii"))
        port.flush()
        ack = port.read_until(b"#", size=12)
        if ack not in (expected.encode("ascii"), (expected + "#").encode("ascii")):
            raise MountProtocolError(f"AM3N rejected {command[:3]} (reply {ack!r})")

    def _service_goto(self, port):
        """Sole serial owner; pending GoTo may be cancelled by Stop."""
        with self._lock:
            pending = self._goto_pending
            if pending is None or self._stop_pending or self._stop.is_set():
                return
            self._goto_pending = None
            self._state["goto_phase"] = "sending"
        name, ra, dec = pending
        try:
            commands = goto_commands(ra, dec)
            for command in commands[:2]:
                with self._lock:
                    if self._stop_pending or self._stop.is_set():
                        return
                self._write_goto(port, command, "1")
            # Lock around the actual start command: a concurrent Stop cannot
            # slip between checking pending Stop and writing :MS.
            with self._lock:
                if self._stop_pending or self._stop.is_set():
                    return
                self._ever_moved = True
                self._write_goto(port, commands[2], "0")
                self._goto_started_at = self._clock()
                self._state.update(goto_phase="slewing", motion_phase="goto_slewing")
        except (MountProtocolError, OSError, serial.SerialException) as exc:
            with self._lock:
                self._queue_stop_locked("GoTo command failed")
                self._state.update(goto_phase="error", goto_error=str(exc))

    def _check_goto(self, parsed):
        with self._lock:
            if self._state["goto_phase"] != "slewing" or not self._goto_coords:
                return
            ra, dec = self._goto_coords
            error = angular_error_deg(ra, dec,
                                      parsed["ra_hours"] * 15, parsed["dec_deg"])
            self._state["goto_position_error_deg"] = round(error, 3)
            if parsed["slewing"] is False and error < 0.35:
                self._goto_stable_count += 1
            else:
                self._goto_stable_count = 0
            if self._goto_stable_count >= 2:
                self._state.update(goto_phase="completed", motion_phase="idle")
                self._ever_moved = False
            elif (self._goto_started_at is not None and
                  self._clock() - self._goto_started_at > GOTO_TIMEOUT_SECONDS):
                self._queue_stop_locked("GoTo timeout")
                self._state.update(goto_phase="error",
                                   goto_error="GoTo did not reach its reported target within five minutes")

    def _write_motion(self, port, command):
        if command not in (
            STOP_COMMAND, *JOG_COMMANDS.values(),
            *JOG_SPEEDS.values()
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
            if (self._state["motion_phase"] in ("starting", "moving") and
                    now >= self._motion_deadline):
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
                # a rate request is ignored, the mount should remain at the
                # verified 8x rate, not inherit an unknown hand-controller rate.
                self._write_motion(port, JOG_RATE)
                if speed != "slow":
                    self._write_motion(port, JOG_SPEEDS[speed])
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

    def _write_clock(self, port, command):
        """Setter ACK is one byte ('1'), unlike #-terminated read responses.

        No browser endpoint can supply a command or trigger this independently.
        """
        if not re.fullmatch(
            r":(?:SG\+00:00|SC\d{2}/\d{2}/\d{2}|SL\d{2}:\d{2}:\d{2})#",
            command,
        ):
            raise ClockSyncError("Refusing unapproved mount clock command")
        if self._stop.is_set():
            raise InterruptedError("Mount disconnect requested")
        port.write(command.encode("ascii"))
        port.flush()
        ack = port.read(1)
        if ack != b"1":
            raise ClockSyncError(f"Mount rejected {command[:3]} clock setter")

    def _sync_clock_on_connect(self, port):
        """Attempt automatic UTC sync ONCE, on the serial owner.

        Failure is visible in status but does not disable manual mount use.
        No GoTo/tracking is available, so unverified time never causes a
        celestial slew. Operators can reconnect once Pi NTP becomes ready.
        """
        try:
            if not self._ntp_checker():
                raise ClockSyncError(
                    "Pi has not confirmed NTP sync (timedatectl NTPSynchronized=no); "
                    "mount clock was left unchanged. Reconnect after NTP sync."
                )
            moment = self._utc_clock()
            commands = utc_sync_commands(moment)
            with self._lock:
                self._state["time_sync_phase"] = "syncing"
            for command in commands:
                self._write_clock(port, command)
            offset = self._query(port, ":GG#")
            date = self._query(port, ":GC#")
            clock = self._query(port, ":GL#")
            if offset != "+00:00":
                raise ClockSyncError(f"Mount UTC offset readback mismatch: {offset!r}")
            mount_time = parse_mount_utc(date, clock)
            now = self._utc_clock().astimezone(timezone.utc)
            delta = abs((mount_time - now).total_seconds())
            if delta > CLOCK_VERIFY_TOLERANCE_SECONDS:
                raise ClockSyncError(
                    f"Mount clock verification failed: offset {delta:.1f}s"
                )
            with self._lock:
                if not self._stop.is_set():
                    self._state.update(
                        time_sync_phase="verified", time_sync_error=None,
                        time_sync_verified_utc=now.isoformat(),
                        environment_phase="queued",
                    )
                    self._environment_pending = True
        except (ClockSyncError, OSError, serial.SerialException, ValueError) as exc:
            with self._lock:
                if not self._stop.is_set():
                    self._state.update(
                        time_sync_phase="error", time_sync_error=str(exc),
                        time_sync_verified_utc=None,
                    )

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
        self._check_goto(parsed)

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
            self._sync_clock_on_connect(port)
            last_poll = -float("inf")
            while not self._stop.is_set():
                self._service_motion(port)
                self._service_goto(port)
                now = self._clock()
                with self._lock:
                    phase = self._state["motion_phase"]
                interval = min(self._interval, 0.35) if phase in ("moving", "starting", "stopping", "goto_queued", "goto_slewing") else self._interval
                if now - last_poll >= interval:
                    self._poll(port)
                    last_poll = self._clock()
                self._service_environment(port)
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
                              self._state["motion_phase"] in ("moving","starting","stopping","goto_queued","goto_slewing"))
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
                    stop_stable=False, environment_phase="idle",
                    environment=None, environment_updated_utc=None,
                    environment_error=None, time_sync_phase="idle",
                    time_sync_error=None, time_sync_verified_utc=None,
                    goto_phase="idle", goto_target=None, goto_error=None,
                    goto_requested_utc=None, goto_position_error_deg=None,
                    **_TELEMETRY,
                )
