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
    assert known_flags("?XYZ") == {
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
