"""AM3N read-only protocol tests with an entirely simulated serial device.

No genuine USB/serial access occurs in CI. Connect is explicit, and no tests
authorize motion, tracking, clock/site or Home/Park setter commands.
"""
import time

import pytest

from astropi.config import Settings
from astropi.mount.worker import (
    MountWorker, MountProtocolError, QUERIES, angle_degrees, ra_hours, known_flags
)
from astropi.web import create_app


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
        if cmd in (":R5#", ":Rv20.00#", ":Rv60.00#", ":Q#", ":Mn#", ":Ms#", ":Me#", ":Mw#"):
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


def test_manual_jog_requires_arm_and_server_stop_confirms_stable(tmp_path):
    alias = tmp_path / "port"
    alias.touch()
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.08)
    with pytest.raises(RuntimeError, match="Connect"):
        worker.arm()
    with pytest.raises(ValueError):
        worker.jog(":hC#")
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    with pytest.raises(RuntimeError, match="Enable"):
        worker.jog("north")
    worker.arm()
    assert worker.status()["motion_armed"]
    worker.jog("east")
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
        worker.arm()  # while stability has yet to be established
    wait_until(lambda: worker.status()["stop_stable"], timeout=5)
    assert worker.status()["motion_phase"] == "idle"
    assert worker.status()["motion_armed"] is False
    assert worker.status()["motion_direction"] is None
    with pytest.raises(RuntimeError, match="Enable"):
        worker.jog("east")  # never automatically re-arm
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
    worker.arm()
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
    worker.arm()
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
    assert client.post("/api/mount/arm").status_code == 403
    assert client.post("/api/mount/jog", json={"direction":"east"}).status_code == 403
    assert client.post("/api/mount/jog-heartbeat", json={"direction":"east"}).status_code == 403
    assert client.post("/api/mount/stop").status_code == 409  # not connected
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control": token}
    assert client.post("/api/mount/connect", headers=headers).status_code == 202
    wait_until(lambda: worker.status()["connected"])
    assert client.post("/api/mount/jog", headers=headers, json={"direction":"north"}).status_code == 409
    assert client.post("/api/mount/arm", headers=headers).status_code == 200
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



def test_hard_jog_time_limit_with_ongoing_heartbeats(tmp_path):
    alias = tmp_path / "port"
    alias.touch()
    factory = MotionFactory()
    worker = MountWorker(alias, serial_factory=factory, poll_interval=0.07)
    worker.connect()
    wait_until(lambda: worker.status()["connected"])
    worker.arm()
    worker.jog("east")
    wait_until(lambda: ":Me#" in factory.ports[0].commands)
    # Periodic renewals do not allow unlimited movement.
    began = time.monotonic()
    while time.monotonic() - began < 4 and ":Q#" not in factory.ports[0].commands:
        try:
            worker.heartbeat("east")
        except RuntimeError:
            pass
        time.sleep(0.15)
    assert ":Q#" in factory.ports[0].commands
    assert worker.status()["last_stop_reason"] == "Maximum jog duration reached"
    assert not worker.status()["motion_armed"]
    worker.disconnect()
    worker._thread.join(timeout=3)



def test_manual_speed_presets_have_safe_whitelist_and_time_caps(tmp_path):
    from astropi.mount.worker import JOG_SPEEDS
    assert JOG_SPEEDS == {
        "slow": (":R5#", 3.0),
        "medium": (":Rv20.00#", 2.0),
        "fast": (":Rv60.00#", 1.0),
    }
    alias=tmp_path / "port"
    alias.touch()
    factory=MotionFactory()
    worker=MountWorker(alias,serial_factory=factory,poll_interval=0.06)
    worker.connect()
    wait_until(lambda:worker.status()["connected"])
    for speed,(rate,seconds) in JOG_SPEEDS.items():
        worker.arm()
        with pytest.raises(ValueError):
            worker.jog("east",speed=":Rv1440#")
        with pytest.raises(ValueError):
            worker.jog("east",speed=1440)
        worker.jog("east",speed=speed)
        wait_until(lambda:worker.status()["motion_phase"]=="moving")
        port=factory.ports[0]
        assert port.commands.index(rate) < max(i for i,v in enumerate(port.commands) if v==":Me#")
        assert worker.status()["jog_speed"]==speed
        remaining=worker._hard_deadline-worker._clock()
        assert 0 < remaining <= seconds
        worker.emergency_stop()
        wait_until(lambda:worker.status()["stop_stable"],timeout=5)
        assert not worker.status()["motion_armed"]
    worker.disconnect()
    worker._thread.join(timeout=3)


def test_fast_speed_caps_at_one_second_even_with_keepalive(tmp_path):
    alias=tmp_path / "port"
    alias.touch()
    factory=MotionFactory()
    worker=MountWorker(alias,serial_factory=factory,poll_interval=0.06)
    worker.connect()
    wait_until(lambda:worker.status()["connected"])
    worker.arm()
    worker.jog("north",speed="fast")
    wait_until(lambda:":Mn#" in factory.ports[0].commands)
    end=time.monotonic()+2.3
    while time.monotonic()<end and ":Q#" not in factory.ports[0].commands:
        try:
            worker.heartbeat("north")
        except RuntimeError:
            break
        time.sleep(0.12)
    # HTTP heartbeat can discover expiry before the serial-owner thread
    # finishes its queued Stop write. Wait for the actual :Q# transmission.
    wait_until(lambda:":Q#" in factory.ports[0].commands,timeout=3)
    assert worker.status()["last_stop_reason"]=="Maximum jog duration reached"
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
    assert client.post("/api/mount/arm",headers=headers).status_code==200
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
