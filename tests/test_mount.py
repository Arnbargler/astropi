"""AM3N serial, motion and UTC-clock tests using simulated hardware.

CI never accesses physical serial ports. Tests cover the approved manual
motion and UTC clock command whitelist; not Home, Park or GoTo setters.
"""
import time

import pytest

from astropi.config import Settings
from astropi.mount.worker import (
    MountWorker, MountProtocolError, QUERIES, angle_degrees, ra_hours, known_flags
)
# Capture real NTP probe before autouse fake replaces the module symbol.
from astropi.mount.worker import system_ntp_synchronized as real_system_ntp_synchronized
from astropi.web import create_app


@pytest.fixture(autouse=True)
def default_no_host_ntp_in_serial_tests(monkeypatch):
    # Existing fake serial tests never depend on CI runner's system clock.
    # New sync tests explicitly inject a synchronized Pi and deterministic UTC.
    monkeypatch.setattr("astropi.mount.worker.system_ntp_synchronized",
                        lambda: False)


RESPONSES = {
    ":GVP#": "AM3N", ":GV#": "1.8.8", ":GU#": "nNHZM040400990",
    ":GA#": "+01*30:50", ":GZ#": "013*43:10",
    ":GR#": "12:34:56", ":GD#": "-22*15:30",
}


def wait_until(test, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if test():
            return
        time.sleep(0.01)
    pytest.fail("Timed out waiting for the fake AM3N worker")


class FakePort:
    def __init__(self, responses=None, *, fail_on=None):
        self.responses = responses or RESPONSES
        self.fail_on = fail_on
        self.commands = []
        self.closed = False
        self.last = None

    def write(self, data):
        cmd = data.decode("ascii")
        if cmd not in QUERIES:
            raise AssertionError("Not a read-only mount query")
        self.commands.append(cmd)
        self.last = cmd

    def flush(self):
        pass

    def read_until(self, expected, size):
        assert expected == b"#"
        assert size <= 96
        if self.last == self.fail_on:
            raise OSError("simulated serial disconnection")
        return (self.responses[self.last] + "#").encode("ascii")

    def close(self):
        self.closed = True


class FakeFactory:
    def __init__(self, **port_kwargs):
        self.ports = []
        self.port_kwargs = port_kwargs

    def __call__(self, **kwargs):
        assert kwargs["baudrate"] == 9600
        assert kwargs["timeout"] <= 1.0
        assert kwargs["write_timeout"] <= 1.0
        assert kwargs["bytesize"] == 8
        assert kwargs["stopbits"] == 1
        assert kwargs["parity"] == "N"
        obj = FakePort(**self.port_kwargs)
        self.ports.append(obj)
        return obj


def test_parser_and_verified_status_only():
    assert angle_degrees("+01*30:50", signed=True) == round(1 + 30/60 + 50/3600, 6)
    assert angle_degrees("-22*15:30", signed=True) == -22.258333
    assert angle_degrees("013*43:10", limit=360) == round(13 + 43/60 + 10/3600, 6)
    assert ra_hours("12:34:56") == round(12 + 34/60 + 56/3600, 7)
    assert known_flags("nNHZM040400990") == {
        "tracking": False, "slewing": False, "at_home": True,
        "altaz_mode": True,
    }
    # Real Pi screenshot: with the optional H missing, Z moves one position.
    assert known_flags("nNZM0000000000") == {
        "tracking": False, "slewing": False, "at_home": None,
        "altaz_mode": True,
    }
    # Never interpret unknown M-suffix characters as mount state flags.
    assert known_flags("nNMZ99") == {
        "tracking": False, "slewing": False, "at_home": None,
        "altaz_mode": None,
    }
    assert known_flags("?XY?") == {
        "tracking": None, "slewing": None, "at_home": None,
        "altaz_mode": None,
    }
    for val in ("91*00:00", "+90*00:01", "+01*67:00", "oops", "12:00:00"):
        with pytest.raises(MountProtocolError):
            angle_degrees(val, signed=True)
    for val in ("25:00:00", "12:60:00", "12:20:70", "garbage"):
        with pytest.raises(MountProtocolError):
            ra_hours(val)


def test_serial_connection_poll_disconnect_and_explicit_reconnect(tmp_path):
    alias = tmp_path / "mount-by-id"
    alias.touch()
    factory = FakeFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.05)
    assert worker.status()["phase"] == "disconnected"
    assert not factory.ports  # no serial open at Flask startup
    assert worker.connect()
    wait_until(lambda: worker.status()["connected"])
    live = worker.status()
    assert live["model"] == "AM3N"
    assert live["firmware"] == "1.8.8"
    assert live["altitude_text"] == "+01*30:50"
    assert live["azimuth_text"] == "013*43:10"
    assert live["ra_hours"] == round(12 + 34/60 + 56/3600, 7)
    assert live["dec_deg"] == -22.258333
    assert live["updated_utc"]
    assert not worker.connect()
    assert worker.disconnect()
    worker._thread.join(timeout=3)
    assert worker.status()["phase"] == "disconnected"
    assert worker.status()["altitude_text"] is None
    assert factory.ports[0].closed
    assert worker.connect()
    wait_until(lambda: worker.status()["connected"])
    assert worker.disconnect()
    worker._thread.join(timeout=3)
    assert len(factory.ports) == 2
    assert all(p.closed for p in factory.ports)
    assert set(sum((port.commands for port in factory.ports), [])) <= QUERIES


def test_serial_unplug_clears_stale_coordinates_and_records_error(tmp_path):
    alias = tmp_path / "mount-by-id"
    alias.touch()
    class FailingFactory(FakeFactory):
        def __call__(self, **kwargs):
            obj = super().__call__(**kwargs)
            # First status poll good, second status poll simulates USB failure.
            read = obj.read_until
            def failing(expected, size):
                if obj.last == ":GU#" and obj.commands.count(":GU#") >= 2:
                    raise OSError("simulated unplug")
                return read(expected, size)
            obj.read_until = failing
            return obj

    factory = FailingFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.02)
    assert worker.connect()
    wait_until(lambda: worker.status()["phase"] == "error")
    state = worker.status()
    assert not state["connected"]
    assert "simulated unplug" in state["last_error"]
    assert state["ra_text"] is None
    assert state["azimuth_deg"] is None
    assert factory.ports[0].closed


def test_mount_model_mismatch_and_bad_reply_fail_closed(tmp_path):
    alias = tmp_path / "mount-by-id"
    alias.touch()
    factory = FakeFactory(responses={**RESPONSES, ":GVP#": "NotAM3N"})
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.01)
    assert worker.connect()
    wait_until(lambda: worker.status()["phase"] == "error")
    assert "Unexpected mount model" in worker.status()["last_error"]
    assert factory.ports[0].commands == [":GVP#"]
    assert factory.ports[0].closed

    class Truncated(FakeFactory):
        def __call__(self, **kwargs):
            port = super().__call__(**kwargs)
            def no_hash(expected, size):
                return b"partial"
            port.read_until = no_hash
            return port
    worker2 = MountWorker(alias, serial_factory=Truncated(), poll_interval=0.01)
    assert worker2.connect()
    wait_until(lambda: worker2.status()["phase"] == "error")
    assert "No complete mount response" in worker2.status()["last_error"]


def test_serial_alias_missing_does_not_open_port(tmp_path):
    factory = FakeFactory()
    worker = MountWorker(tmp_path / "missing-by-id", serial_factory=factory)
    assert worker.connect()
    wait_until(lambda: worker.status()["phase"] == "error")
    assert not factory.ports
    assert worker.status()["altitude_text"] is None


def test_mount_http_operator_auth_and_viewer_status(tmp_path):
    alias = tmp_path / "mount-by-id"
    alias.touch()
    factory = FakeFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.02)
    settings = Settings(tmp_path, "expected", alias, tmp_path / "usb-none")
    client = create_app(settings=settings, mount=worker).test_client()
    assert not factory.ports  # no hidden mount open from status request
    assert client.get("/api/status").get_json()["mount"]["phase"] == "disconnected"
    assert client.get("/api/mount/status").status_code == 200
    assert client.post("/api/mount/connect").status_code == 403
    assert client.post("/api/mount/disconnect").status_code == 403
    assert client.post("/api/mount/command", json={"cmd":":Me#"}).status_code == 404
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control": token}
    assert client.post("/api/mount/connect", headers=headers).status_code == 202
    wait_until(lambda: worker.status()["connected"])
    assert client.get("/api/status").get_json()["mount"]["azimuth_text"] == "013*43:10"
    assert client.get("/api/mount/status").get_json()["model"] == "AM3N"
    assert client.post("/api/mount/connect", headers=headers).status_code == 409
    assert client.post("/api/mount/disconnect", headers=headers).status_code == 202
    worker._thread.join(timeout=3)
    assert not worker.status()["connected"]



class MotionPort(FakePort):
    """Only accepts the three explicitly allowed *types* of manual command."""
    def write(self, data):
        cmd = data.decode("ascii")
        if cmd in (":R5#", ":Rv20.00#", ":Rv60.00#", ":R8#", ":R9#", ":Q#", ":Mn#", ":Ms#", ":Me#", ":Mw#"):
            self.commands.append(cmd)
            self.last = cmd
            return
        super().write(data)


class MotionFactory(FakeFactory):
    def __call__(self, **kwargs):
        assert kwargs["baudrate"] == 9600
        port = MotionPort()
        self.ports.append(port)
        return port


def test_manual_jog_starts_immediately_and_server_stop_confirms_stable(tmp_path):
    alias = tmp_path / "port"
    alias.touch()
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.08)
    with pytest.raises(RuntimeError, match="Connect"):
        worker.jog("east")
    with pytest.raises(ValueError):
        worker.jog(":hC#")
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    worker.jog("east")
    assert worker.status()["motion_armed"]
    wait_until(lambda: ":Me#" in factory.ports[0].commands)
    commands=factory.ports[0].commands
    assert commands.index(":R5#") < commands.index(":Me#")
    assert worker.status()["motion_phase"] == "moving"
    with pytest.raises(RuntimeError, match="Only one"):
        worker.jog("north")
    assert worker.heartbeat("east")
    assert worker.emergency_stop()
    wait_until(lambda: ":Q#" in commands)
    assert worker.status()["last_stop_sent_utc"]
    with pytest.raises(RuntimeError):
        worker.jog("west")  # cannot reverse while Stop is settling
    wait_until(lambda: worker.status()["stop_stable"], timeout=5)
    assert worker.status()["motion_phase"] == "idle"
    assert worker.status()["motion_armed"] is False
    assert worker.status()["motion_direction"] is None
    worker.jog("east")  # immediately available once axes settle
    wait_until(lambda: factory.ports[0].commands.count(":Me#") == 2)
    worker.emergency_stop()
    wait_until(lambda: worker.status()["stop_stable"], timeout=5)
    assert worker.disconnect()
    worker._thread.join(timeout=3)
    assert factory.ports[0].closed


def test_server_deadman_automatically_stops_without_browser_heartbeat(tmp_path):
    alias = tmp_path / "port"
    alias.touch()
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.08)
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    worker.jog("north")
    wait_until(lambda: ":Mn#" in factory.ports[0].commands)
    # No heartbeat: timer belongs to the Pi, NOT to browser JavaScript.
    wait_until(lambda: ":Q#" in factory.ports[0].commands, timeout=3)
    state = worker.status()
    assert state["last_stop_reason"] == "Deadman heartbeat expired"
    assert state["motion_armed"] is False
    with pytest.raises(RuntimeError):
        worker.heartbeat("north")  # expired request cannot revive motion
    wait_until(lambda: worker.status()["stop_stable"], timeout=5)
    worker.disconnect()
    worker._thread.join(timeout=3)


def test_disconnect_during_jog_attempts_stop_before_serial_close(tmp_path):
    alias = tmp_path / "port"
    alias.touch()
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.04)
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    worker.jog("west")
    wait_until(lambda: ":Mw#" in factory.ports[0].commands)
    assert worker.disconnect()
    worker._thread.join(timeout=3)
    port = factory.ports[0]
    assert port.closed
    assert ":Q#" in port.commands[port.commands.index(":Mw#"):]
    assert worker.status()["phase"] == "disconnected"
    assert worker.status()["azimuth_deg"] is None


def test_http_jog_requires_lease_and_stop_does_not(tmp_path):
    alias = tmp_path / "port"
    alias.touch()
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.06)
    settings = Settings(tmp_path, "expected", alias, tmp_path / "usb")
    client = create_app(settings=settings, mount=worker).test_client()
    assert client.post("/api/mount/arm").status_code == 404
    assert client.post("/api/mount/jog", json={"direction":"east"}).status_code == 403
    assert client.post("/api/mount/jog-heartbeat", json={"direction":"east"}).status_code == 403
    assert client.post("/api/mount/stop").status_code == 409  # not connected
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control": token}
    assert client.post("/api/mount/connect", headers=headers).status_code == 202
    wait_until(lambda: worker.status()["connected"])
    assert client.post("/api/mount/jog", headers=headers, json={"direction":"north"}).status_code == 202
    assert client.post("/api/mount/stop").status_code == 202
    wait_until(lambda: worker.status()["stop_stable"], timeout=5)
    assert client.post("/api/mount/jog", headers=headers, json={"direction":":hC#"}).status_code == 400
    assert client.post("/api/mount/jog", headers=headers, json={"direction":"south"}).status_code == 202
    wait_until(lambda: ":Ms#" in factory.ports[0].commands)
    # Any LAN viewer may request a safety Stop, never initiate motion.
    assert client.post("/api/mount/stop").status_code == 202
    wait_until(lambda: ":Q#" in factory.ports[0].commands)
    with pytest.raises(RuntimeError):
        worker.heartbeat("south")
    worker.disconnect()
    worker._thread.join(timeout=3)


def test_emergency_stop_from_idle_is_explicit_serial_stop(tmp_path):
    alias = tmp_path / "port"
    alias.touch()
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.07)
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    worker.emergency_stop()
    wait_until(lambda: ":Q#" in factory.ports[0].commands)
    assert ":Mn#" not in factory.ports[0].commands
    assert ":Me#" not in factory.ports[0].commands
    wait_until(lambda: worker.status()["stop_stable"], timeout=5)
    worker.disconnect()
    worker._thread.join(timeout=3)



def test_continuous_jog_is_not_time_limited_while_heartbeats_arrive(tmp_path):
    """Simulate 15+ seconds of holding the button without sleeping 15s."""
    alias = tmp_path / "port"
    alias.touch()
    now = [100.0]
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.07,
                         clock=lambda: now[0])
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    worker.jog("east")
    wait_until(lambda: ":Me#" in factory.ports[0].commands)
    for _ in range(60):
        now[0] += 0.3
        assert worker.heartbeat("east")
        time.sleep(0.005)
    assert worker.status()["motion_phase"] == "moving"
    assert worker.status()["motion_armed"]
    assert ":Q#" not in factory.ports[0].commands
    # Release-to-Stop is still required and is not assumed completed yet.
    worker.emergency_stop("Button released")
    wait_until(lambda: ":Q#" in factory.ports[0].commands)
    assert worker.status()["last_stop_reason"] == "Button released"
    assert not worker.status()["motion_armed"]
    worker.disconnect()
    worker._thread.join(timeout=3)

def test_manual_speed_presets_are_whitelisted_without_duration_caps(tmp_path):
    from astropi.mount.worker import JOG_SPEEDS
    assert JOG_SPEEDS == {
        "slow": ":R5#",
        "medium": ":Rv20.00#",
        "fast": ":Rv60.00#",
        "slew": ":R8#",
        "max": ":R9#",
    }
    alias = tmp_path / "port"
    alias.touch()
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.06)
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    for speed, rate in JOG_SPEEDS.items():
        for bad in (":Rv1440#", 1440, None):
            with pytest.raises(ValueError):
                worker.jog("east", speed=bad)
        worker.jog("east", speed=speed)
        wait_until(lambda: worker.status()["motion_phase"] == "moving")
        commands = factory.ports[0].commands
        assert commands.index(rate) < max(i for i, cmd in enumerate(commands) if cmd == ":Me#")
        assert worker.status()["jog_speed"] == speed
        assert worker.heartbeat("east")
        assert not hasattr(worker, "_hard_deadline")
        worker.emergency_stop()
        wait_until(lambda: worker.status()["stop_stable"], timeout=5)
        assert not worker.status()["motion_armed"]
    worker.disconnect()
    worker._thread.join(timeout=3)

def test_fast_jog_can_continue_past_old_one_second_limit(tmp_path):
    alias = tmp_path / "port"
    alias.touch()
    now = [50.0]
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.06,
                         clock=lambda: now[0])
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    worker.jog("north", speed="fast")
    wait_until(lambda: ":Mn#" in factory.ports[0].commands)
    for _ in range(15):
        now[0] += 0.2
        assert worker.heartbeat("north")
        time.sleep(0.007)
    assert worker.status()["motion_phase"] == "moving"
    assert ":Q#" not in factory.ports[0].commands
    worker.emergency_stop()
    wait_until(lambda: ":Q#" in factory.ports[0].commands)
    worker.disconnect()
    worker._thread.join(timeout=3)

def test_unknown_jog_speed_http_rejected_without_any_motion(tmp_path):
    alias=tmp_path / "port"
    alias.touch()
    factory=MotionFactory()
    worker=MountWorker(alias,serial_factory=factory,poll_interval=0.06)
    client=create_app(settings=Settings(tmp_path,"expected",alias,tmp_path/"usb"),
                      mount=worker).test_client()
    token=client.post("/api/control/take").get_json()["token"]
    headers={"X-AstroPi-Control":token}
    assert client.post("/api/mount/connect",headers=headers).status_code==202
    wait_until(lambda:worker.status()["connected"])
    assert client.post("/api/mount/arm",headers=headers).status_code==404
    for invalid in (":Rv1440#",1440,{},None,"turbo"):
        result=client.post("/api/mount/jog",headers=headers,json={
            "direction":"east","speed":invalid})
        assert result.status_code==400
    assert ":Me#" not in factory.ports[0].commands
    assert client.post("/api/mount/jog",headers=headers,json={
        "direction":"east","speed":"medium"}).status_code==202
    wait_until(lambda:":Rv20.00#" in factory.ports[0].commands)
    assert client.post("/api/mount/stop").status_code==202
    worker.disconnect()
    worker._thread.join(timeout=3)



def test_mount_clock_site_readout_is_explicit_and_read_only(tmp_path):
    from astropi.mount.worker import ENVIRONMENT_QUERIES
    alias = tmp_path / "serial"
    alias.touch()
    responses = {
        **RESPONSES,
        ":GG#": "+00:00",
        ":GC#": "10/28/26",
        ":GL#": "07:41:24",
        ":Gt#": "+45*17:36",
        ":Gg#": "+075*51:26",
        ":GS#": "12:32:54",
    }
    factory = FakeFactory(responses=responses)
    mount = MountWorker(alias, serial_factory=factory, poll_interval=0.06)
    mount.connect()
    wait_until(lambda: mount.status()["connected"])
    assert not any(cmd in factory.ports[0].commands
                   for cmd in ENVIRONMENT_QUERIES.values())
    assert mount.status()["environment"] is None
    mount.request_environment_read()
    with pytest.raises(RuntimeError):
        mount.request_environment_read()
    wait_until(lambda: mount.status()["environment_phase"] == "ready")
    result = mount.status()["environment"]
    assert result == {
        "utc_offset": "+00:00", "date": "10/28/26",
        "local_time": "07:41:24", "latitude": "+45*17:36",
        "longitude_west": "+075*51:26", "sidereal_time": "12:32:54",
    }
    assert mount.status()["environment_updated_utc"]
    # Clock/site are read and NEVER modified through this interface.
    assert set(factory.ports[0].commands) <= QUERIES
    assert all(cmd in factory.ports[0].commands for cmd in ENVIRONMENT_QUERIES.values())
    assert mount.disconnect()
    mount._thread.join(timeout=3)
    assert mount.status()["environment"] is None
    assert mount.status()["environment_phase"] == "idle"


def test_clock_site_readout_requires_lease_and_idle_mount(tmp_path):
    alias = tmp_path / "serial"
    alias.touch()
    responses = {**RESPONSES,
        ":GG#": "+00:00", ":GC#": "10/28/26",
        ":GL#": "07:41:24", ":Gt#": "+45*17:36",
        ":Gg#": "+075*51:26", ":GS#": "12:32:54"}
    class EnvMotionFactory(FakeFactory):
        def __call__(self, **kwargs):
            port = MotionPort(responses=responses)
            self.ports.append(port)
            return port

    factory = EnvMotionFactory()
    mount = MountWorker(alias, serial_factory=factory, poll_interval=0.06)
    client = create_app(settings=Settings(tmp_path, "expected", alias, tmp_path / "usb"),
                        mount=mount).test_client()
    assert client.post("/api/mount/environment/read").status_code == 403
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control": token}
    assert client.post("/api/mount/environment/read", headers=headers).status_code == 409
    client.post("/api/mount/connect", headers=headers)
    wait_until(lambda: mount.status()["connected"])
    mount.jog("east")
    wait_until(lambda: ":Me#" in factory.ports[0].commands)
    assert client.post("/api/mount/environment/read", headers=headers).status_code == 409
    mount.emergency_stop()
    wait_until(lambda: mount.status()["stop_stable"], timeout=5)
    assert client.post("/api/mount/environment/read", headers=headers).status_code == 202
    wait_until(lambda: mount.status()["environment_phase"] == "ready")
    assert client.get("/api/mount/status").get_json()["environment"]["date"] == "10/28/26"
    mount.disconnect()
    mount._thread.join(timeout=3)


def test_full_slew_rates_without_arm_and_stop_priority(tmp_path):
    alias = tmp_path / "port"
    alias.touch()
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.05)
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    for speed, cmd in (("slew", ":R8#"), ("max", ":R9#")):
        port = factory.ports[0]
        before = len(port.commands)
        worker.jog("east", speed=speed)
        wait_until(lambda: port.commands.count(":Me#") >= (1 if speed == "slew" else 2))
        steps = port.commands[before:]
        assert steps.index(":R5#") < steps.index(cmd) < steps.index(":Me#")
        assert worker.status()["jog_speed"] == speed
        assert worker.heartbeat("east")
        with pytest.raises(RuntimeError, match="Only one"):
            worker.jog("north", speed="slow")
        worker.emergency_stop()
        wait_until(lambda: worker.status()["stop_stable"], timeout=5)
    worker.disconnect()
    worker._thread.join(timeout=3)


def test_stop_pending_blocks_direct_jog_before_axes_stabilize(tmp_path):
    alias = tmp_path / "port"
    alias.touch()
    worker = MountWorker(alias, serial_factory=MotionFactory(), poll_interval=0.05)
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    worker.jog("east", speed="slew")
    worker.emergency_stop()
    with pytest.raises(RuntimeError):
        worker.jog("east")
    wait_until(lambda: worker.status()["stop_stable"], timeout=5)
    worker.disconnect()
    worker._thread.join(timeout=3)



class ClockSyncFakePort(FakePort):
    """Simulate AM3N's single-byte setter ACK plus #-terminated getters."""
    def __init__(self, *, failed_ack=None, old_readback=False, bad_site=False):
        super().__init__({
            **RESPONSES,
            ":GG#": "+00:00", ":GC#": "01/01/00", ":GL#": "01:12:54",
            ":Gt#": "+45*17:36", ":Gg#": "+075*51:26", ":GS#": "01:13:07",
        })
        self.failed_ack = failed_ack
        self.old_readback = old_readback
        self.bad_site = bad_site
        if bad_site:
            # Incorrect location that remains incorrect after accepted ACKs.
            self.responses[":Gt#"] = "+44*10:00"

    def write(self, data):
        cmd = data.decode("ascii")
        if cmd.startswith((":SG", ":SC", ":SL", ":St", ":Sg")):
            self.commands.append(cmd)
            self.last = cmd
            if not self.old_readback:
                if cmd.startswith(":SG"):
                    self.responses[":GG#"] = cmd[3:-1]
                elif cmd.startswith(":SC"):
                    self.responses[":GC#"] = cmd[3:-1]
                elif cmd.startswith(":SL"):
                    self.responses[":GL#"] = cmd[3:-1]
                elif cmd.startswith(":St") and not self.bad_site:
                    self.responses[":Gt#"] = cmd[3:-1] + ":00"
                elif cmd.startswith(":Sg") and not self.bad_site:
                    self.responses[":Gg#"] = "+" + cmd[3:-1] + ":00"
            return
        super().write(data)

    def read(self, length):
        assert length == 1
        return b"0" if self.last.startswith(self.failed_ack or "NEVER") else b"1"


class ClockSyncFactory(FakeFactory):
    def __init__(self, **kw):
        super().__init__()
        self.kw = kw

    def __call__(self, **kwargs):
        assert kwargs["baudrate"] == 9600
        port = ClockSyncFakePort(**self.kw)
        self.ports.append(port)
        return port


def test_utc_mount_setter_format_and_readback_parser():
    from astropi.mount.worker import utc_sync_commands, parse_mount_utc, ClockSyncError
    from datetime import datetime, timedelta, timezone

    toronto = timezone(timedelta(hours=-4))
    instant = datetime(2026, 10, 28, 4, 33, 7, tzinfo=toronto)
    assert utc_sync_commands(instant) == (
        ":SG+00:00#", ":SC10/28/26#", ":SL08:33:07#"
    )
    assert parse_mount_utc("10/28/26", "08:33:07") == instant.astimezone(timezone.utc)
    assert utc_sync_commands(datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc))[1:] == (
        ":SC12/31/26#", ":SL23:59:59#"
    )
    for date, clock in (("02/30/26", "08:00:00"), ("02/28/26", "25:12:00"),
                        ("10/28/26#", "09:00:00"), ("01/01/00", "bad")):
        with pytest.raises(ClockSyncError):
            parse_mount_utc(date, clock)
    with pytest.raises(ClockSyncError):
        utc_sync_commands(datetime(2000,1,1,tzinfo=timezone.utc))
    with pytest.raises(ClockSyncError):
        utc_sync_commands(datetime(2026,10,28,8,33,7))


def test_clock_sync_automatically_on_connect_and_populates_site_snapshot(tmp_path):
    from datetime import datetime, timezone
    port_alias = tmp_path / "by-id-am3"
    port_alias.touch()
    moment = datetime(2026, 10, 28, 8, 33, 7, tzinfo=timezone.utc)
    factory = ClockSyncFactory()
    mount = MountWorker(port_alias, serial_factory=factory, poll_interval=0.05,
                        ntp_checker=lambda: True, utc_clock=lambda: moment)
    assert not factory.ports
    mount.connect()
    wait_until(lambda: mount.status()["time_sync_phase"] == "verified")
    wait_until(lambda: mount.status()["environment_phase"] == "ready")
    assert mount.status()["connected"]
    assert mount.status()["time_sync_verified_utc"] == moment.isoformat()
    assert mount.status()["site_sync_phase"] == "verified"
    assert mount.status()["site_sync_verified_utc"] == moment.isoformat()
    port = factory.ports[0]
    cmds = port.commands
    setters = [c for c in cmds if c.startswith((":SG", ":SC", ":SL"))]
    assert setters == [":SG+00:00#", ":SC10/28/26#", ":SL08:33:07#"]
    assert cmds.index(":St+45*18#") > cmds.index(":SL08:33:07#")
    assert cmds.index(":Sg075*51#") > cmds.index(":St+45*18#")
    assert cmds.index(":GL#") > cmds.index(":Sg075*51#")
    assert mount.status()["environment"]["date"] == "10/28/26"
    assert mount.status()["environment"]["local_time"] == "08:33:07"
    assert mount.status()["environment"]["latitude"] == "+45*18:00"
    assert mount.status()["environment"]["longitude_west"] == "+075*51:00"
    assert not any(c.startswith((":hC", ":MS")) for c in cmds)
    mount.disconnect()
    mount._thread.join(timeout=3)
    assert port.closed
    assert mount.status()["time_sync_phase"] == "idle"
    assert mount.status()["site_sync_phase"] == "idle"
    # A NEW connection sets and verifies live clock and site again.
    mount.connect()
    wait_until(lambda: mount.status()["time_sync_phase"] == "verified")
    assert len(factory.ports) == 2
    mount.disconnect()
    mount._thread.join(timeout=3)


def test_clock_sync_fails_closed_when_pi_ntp_not_synchronized(tmp_path):
    alias = tmp_path / "am3"
    alias.touch()
    factory = ClockSyncFactory()
    mount = MountWorker(alias, serial_factory=factory, poll_interval=0.05,
                        ntp_checker=lambda: False)
    mount.connect()
    wait_until(lambda: mount.status()["connected"])
    state = mount.status()
    assert state["time_sync_phase"] == "error"
    assert state["time_sync_verified_utc"] is None
    assert "not confirmed NTP" in state["time_sync_error"]
    assert not any(c.startswith((":SG", ":SC", ":SL", ":St", ":Sg")) for c in factory.ports[0].commands)
    mount.disconnect()
    mount._thread.join(timeout=3)


@pytest.mark.parametrize("port_args, message", [
    ({"failed_ack":":SC"}, "rejected"),
    ({"failed_ack":":St"}, "rejected"),
    ({"failed_ack":":Sg"}, "rejected"),
    ({"old_readback":True}, "verification failed"),
    ({"bad_site":True}, "site verification failed"),
])
def test_clock_sync_does_not_claim_success_on_rejected_or_stale_readback(
    tmp_path, port_args, message
):
    from datetime import datetime, timezone
    alias = tmp_path / "am3"
    alias.touch()
    fixed = datetime(2026, 10, 28, 8, 33, 7, tzinfo=timezone.utc)
    factory = ClockSyncFactory(**port_args)
    mount = MountWorker(alias, serial_factory=factory, poll_interval=0.05,
                        ntp_checker=lambda: True, utc_clock=lambda: fixed)
    mount.connect()
    wait_until(lambda: mount.status()["connected"])
    assert mount.status()["time_sync_phase"] == "error"
    assert message in mount.status()["time_sync_error"]
    assert mount.status()["time_sync_verified_utc"] is None
    assert mount.status()["site_sync_phase"] == "error"
    assert mount.status()["site_sync_verified_utc"] is None
    # Manually jogging is independent, but no clock/site VERIFIED status is invented.
    mount.disconnect()
    mount._thread.join(timeout=3)


def test_ntp_status_checks_systemd_report_not_merely_service_enabled(monkeypatch):
    from astropi.mount.worker import system_ntp_synchronized
    from subprocess import CompletedProcess, TimeoutExpired
    import astropi.mount.worker as module

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k:
                        CompletedProcess(args=[], returncode=0, stdout="yes\n"))
    assert real_system_ntp_synchronized()
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k:
                        CompletedProcess(args=[], returncode=0, stdout="no\n"))
    assert not real_system_ntp_synchronized()
    def timeout(*args, **kwargs):
        raise TimeoutExpired(cmd="timedatectl", timeout=2)
    monkeypatch.setattr(module.subprocess, "run", timeout)
    assert not real_system_ntp_synchronized()


# --- Catalogue GoTo through the existing single-owner serial worker ---

class GoToFakePort(ClockSyncFakePort):
    """AM3N simulator: setter replies, :MS start, reported target, and Stop."""
    def __init__(self, *, reject_ms=False, arrive=True):
        super().__init__()
        self.reject_ms = reject_ms
        self.arrive = arrive
        self.started = False
        self.target_ra = None
        self.target_dec = None

    def write(self, data):
        cmd = data.decode("ascii")
        if cmd.startswith((":Sr", ":Sd")) or cmd in (":MS#", ":Q#"):
            self.commands.append(cmd)
            self.last = cmd
            if cmd.startswith(":Sr"):
                self.target_ra = cmd[3:-1]
            elif cmd.startswith(":Sd"):
                self.target_dec = cmd[3:-1]
            elif cmd == ":MS#" and not self.reject_ms:
                self.started = True
                if self.arrive:
                    self.responses[":GR#"] = self.target_ra
                    self.responses[":GD#"] = self.target_dec
            return
        super().write(data)

    def read_until(self, expected, size):
        if self.last.startswith((":Sr", ":Sd")):
            return b"1#"
        if self.last == ":MS#":
            return b"1#" if self.reject_ms else b"0#"
        return super().read_until(expected, size)


class GoToFakeFactory(FakeFactory):
    def __init__(self, **kwargs):
        super().__init__()
        self.options = kwargs

    def __call__(self, **kwargs):
        port = GoToFakePort(**self.options)
        self.ports.append(port)
        return port


def test_goto_coordinate_epoch_format_validation():
    from datetime import datetime, timezone
    from astropi.mount.goto import target_of_date, goto_commands, angular_error_deg
    j2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    ra, dec = target_of_date("M31", j2000)
    assert ra == pytest.approx(10.6847083, abs=1e-5)
    assert dec == pytest.approx(41.26875, abs=1e-5)
    assert goto_commands(ra, dec) == (
        ":Sr00:42:44#", ":Sd+41*16:08#", ":MS#")
    assert goto_commands(359.9999, -0.001) == (
        ":Sr00:00:00#", ":Sd-00*00:04#", ":MS#")
    assert angular_error_deg(1, 40, 359, 40) < 2
    for bad in ("M0", "M111", "m31", ":MS#", "M31;rm -rf", 31, None):
        with pytest.raises(ValueError):
            target_of_date(bad, j2000)


def test_goto_real_protocol_sequence_and_reported_completion(tmp_path):
    from datetime import datetime, timezone
    alias = tmp_path / "serial"
    alias.touch()
    fixed = datetime(2026, 10, 31, 22, tzinfo=timezone.utc)
    factory = GoToFakeFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.04,
                         ntp_checker=lambda: True, utc_clock=lambda: fixed)
    app = create_app(settings=Settings(tmp_path, "expected", alias, tmp_path / "usb"),
                     mount=worker).test_client()
    assert app.post("/api/mount/goto", json={"target":"M31"}).status_code == 403
    token = app.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control":token}
    assert app.post("/api/mount/goto", headers=headers,
                    json={"target":"M31"}).status_code == 409
    assert app.post("/api/mount/connect", headers=headers).status_code == 202
    wait_until(lambda: worker.status()["time_sync_phase"] == "verified")
    wait_until(lambda: worker.status()["environment_phase"] == "ready")
    for bad in ({"target":"M0"},{"target":":MS#"},{"target":"m31"},
                {"target":12}, {"ra":12.3,"dec":45.6}):
        assert app.post("/api/mount/goto", headers=headers, json=bad).status_code == 400
    assert app.post("/api/mount/goto", headers=headers,
                    json={"target":"M31"}).status_code == 202
    wait_until(lambda: worker.status()["goto_phase"] == "completed", timeout=5)
    port = factory.ports[0]
    pos = [i for i,x in enumerate(port.commands) if x.startswith(":Sr")]
    assert len(pos) == 1
    assert port.commands[pos[0]].startswith(":Sr")
    assert port.commands[pos[0]+1].startswith(":Sd")
    assert port.commands[pos[0]+2] == ":MS#"
    assert port.commands.index(":SL22:00:00#") < pos[0]
    assert worker.status()["goto_target"] == "M31"
    assert worker.status()["motion_phase"] == "idle"
    assert worker.status()["goto_position_error_deg"] < 0.35
    assert ":St+45*18#" in port.commands and ":Sg075*51#" in port.commands
    assert port.commands.index(":Sg075*51#") < pos[0]
    assert not any(x.startswith((":CM",":hC")) for x in port.commands)
    worker.disconnect()
    worker._thread.join(timeout=3)


def test_goto_viewer_stop_aborts_and_locks_manual_jog(tmp_path):
    from datetime import datetime, timezone
    alias=tmp_path/"serial"
    alias.touch()
    factory=GoToFakeFactory(arrive=False)
    worker=MountWorker(alias, serial_factory=factory, poll_interval=0.04,
                       ntp_checker=lambda: True,
                       utc_clock=lambda: datetime(2026,10,31,22,tzinfo=timezone.utc))
    client=create_app(settings=Settings(tmp_path,"expected",alias,tmp_path/"usb"),
                      mount=worker).test_client()
    token=client.post("/api/control/take").get_json()["token"]
    headers={"X-AstroPi-Control":token}
    client.post("/api/mount/connect", headers=headers)
    wait_until(lambda: worker.status()["time_sync_phase"]=="verified")
    wait_until(lambda: worker.status()["environment_phase"]=="ready")
    assert client.post("/api/mount/goto",headers=headers,json={"target":"M42"}).status_code==202
    wait_until(lambda: ":MS#" in factory.ports[0].commands)
    with pytest.raises(RuntimeError):
        worker.jog("east")
    assert client.post("/api/mount/goto",headers=headers,json={"target":"M31"}).status_code==409
    # A non-operator can still request the physical stop command.
    assert client.post("/api/mount/stop").status_code==202
    wait_until(lambda: ":Q#" in factory.ports[0].commands)
    wait_until(lambda: worker.status()["stop_stable"], timeout=5)
    assert worker.status()["goto_phase"] == "aborted"
    assert not worker.status()["motion_armed"]
    worker.disconnect()
    worker._thread.join(timeout=3)


def test_goto_rejected_ms_fails_closed_and_requests_stop(tmp_path):
    from datetime import datetime, timezone
    alias=tmp_path/"serial"
    alias.touch()
    factory=GoToFakeFactory(reject_ms=True)
    worker=MountWorker(alias, serial_factory=factory, poll_interval=0.04,
                       ntp_checker=lambda: True,
                       utc_clock=lambda: datetime(2026,10,31,22,tzinfo=timezone.utc))
    worker.connect()
    wait_until(lambda: worker.status()["time_sync_phase"]=="verified")
    wait_until(lambda: worker.status()["environment_phase"]=="ready")
    worker.goto("M31")
    wait_until(lambda: worker.status()["goto_phase"]=="error")
    wait_until(lambda: ":Q#" in factory.ports[0].commands)
    assert "rejected" in worker.status()["goto_error"]
    assert worker.status()["goto_phase"] == "error"
    assert ":MS#" in factory.ports[0].commands
    worker.disconnect()
    worker._thread.join(timeout=3)


def test_goto_requires_verified_mount_clock(tmp_path):
    alias=tmp_path/"serial"
    alias.touch()
    factory=GoToFakeFactory()
    worker=MountWorker(alias,serial_factory=factory,poll_interval=0.04,
                       ntp_checker=lambda: False)
    worker.connect()
    wait_until(lambda:worker.status()["connected"])
    with pytest.raises(RuntimeError, match="Verified"):
        worker.goto("M31")
    assert not any(cmd.startswith((":Sr",":Sd",":MS")) for cmd in factory.ports[0].commands)
    worker.disconnect()
    worker._thread.join(timeout=3)


def test_permanent_site_command_format_and_tolerant_readback():
    from astropi.mount.worker import (
        permanent_site_commands, verify_permanent_site, ClockSyncError)
    assert permanent_site_commands() == (":St+45*18#", ":Sg075*51#")
    assert verify_permanent_site("+45*18:00", "+075*51:00")
    assert verify_permanent_site("+45*17:36", "+075*51:26")
    for latitude, longitude in (
        ("+44*59:00", "+075*51:00"),
        ("+45*18:00", "+076*10:00"),
        ("-45*18:00", "+075*51:00"),
    ):
        with pytest.raises(ClockSyncError):
            verify_permanent_site(latitude, longitude)


def test_manual_time_site_resync_endpoint_and_idle_lock(tmp_path):
    from datetime import datetime, timezone
    alias = tmp_path / "am3"
    alias.touch()
    moment = datetime(2026, 10, 31, 20, 5, 6, tzinfo=timezone.utc)
    factory = ClockSyncFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.04,
                         ntp_checker=lambda: True, utc_clock=lambda: moment)
    client = create_app(settings=Settings(tmp_path,"expected",alias,tmp_path/"usb"),
                        mount=worker).test_client()
    assert client.post("/api/mount/environment/sync").status_code == 403
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control": token}
    assert client.post("/api/mount/environment/sync", headers=headers).status_code == 409
    assert client.post("/api/mount/connect", headers=headers).status_code == 202
    wait_until(lambda: worker.status()["site_sync_phase"] == "verified")
    wait_until(lambda: worker.status()["environment_phase"] == "ready")
    old_count = factory.ports[0].commands.count(":St+45*18#")
    assert old_count == 1
    assert client.post("/api/mount/environment/sync", headers=headers).status_code == 202
    assert client.post("/api/mount/environment/sync", headers=headers).status_code == 409
    assert client.post("/api/mount/jog", headers=headers,
                       json={"direction":"east"}).status_code == 409
    wait_until(lambda: factory.ports[0].commands.count(":St+45*18#") == 2)
    wait_until(lambda: worker.status()["environment_phase"] == "ready" and
               worker.status()["site_sync_phase"] == "verified")
    assert worker.status()["site_sync_error"] is None
    assert worker.status()["environment"]["longitude_west"] == "+075*51:00"
    worker.disconnect()
    worker._thread.join(timeout=3)


def test_site_failure_blocks_goto_but_allows_jog(tmp_path):
    from datetime import datetime, timezone
    alias = tmp_path / "am3"
    alias.touch()
    factory = ClockSyncFactory(bad_site=True)
    mount = MountWorker(alias, serial_factory=factory, poll_interval=0.04,
                        ntp_checker=lambda: True,
                        utc_clock=lambda: datetime(2026,10,31,22,tzinfo=timezone.utc))
    mount.connect()
    wait_until(lambda: mount.status()["site_sync_phase"] == "error")
    wait_until(lambda: mount.status()["connected"])
    with pytest.raises(RuntimeError, match="permanent site"):
        mount.goto("M31")
    assert ":MS#" not in factory.ports[0].commands
    mount.disconnect()
    mount._thread.join(timeout=3)
