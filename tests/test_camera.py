import io
import numpy as np
from PIL import Image

from astropi.camera.preview import raw16_to_jpeg, raw16_statistics
from astropi.camera.sdk import RAW_BYTES, WIDTH, HEIGHT
from astropi.camera.worker import CameraWorker
from astropi.config import Settings
from astropi.control import ControlLease
from astropi.web import create_app


def test_preview_jpeg_and_raw_unchanged():
    raw = np.empty((HEIGHT, WIDTH), dtype="<u2")
    raw[0::2, 1::2] = 3000 << 4
    raw[0::2, 0::2] = 2000 << 4
    raw[1::2, 1::2] = 2000 << 4
    raw[1::2, 0::2] = 1000 << 4
    before = raw.copy()
    jpeg = raw16_to_jpeg(raw)
    assert jpeg[:2] == bytes([255, 216])
    assert Image.open(io.BytesIO(jpeg)).size == (WIDTH // 4, HEIGHT // 4)
    assert np.array_equal(raw, before)


def test_preview_rejects_wrong_length():
    try:
        raw16_to_jpeg(bytes(100))
    except ValueError:
        pass
    else:
        raise AssertionError("Short buffer accepted")


def test_lease_expiry_and_release():
    t = [100]
    lease = ControlLease(ttl=15, clock=lambda: t[0])
    token = lease.take()
    assert lease.owns(token)
    assert lease.take() is None
    t[0] += 10
    assert lease.renew(token)
    t[0] += 16
    assert not lease.owns(token)
    later = lease.take()
    assert later and later != token
    assert lease.release(later)


class FakeCamera:
    def status(self):
        return {"phase": "stopped", "last_error": None, "has_frame": False,
                "frame_number": 0, "gain": 0, "exposure_us": 100000}
    def frame(self):
        return None, 0
    def start(self):
        return True
    def stop(self):
        return True
    def configure(self, gain, exposure_us):
        if type(gain) is not int:
            raise ValueError("Invalid gain")
    def set_preview_mode(self, mode):
        if mode not in ("auto", "fixed"):
            raise ValueError("Invalid preview mode")
        return mode


def test_http_requires_lease(tmp_path):
    config = Settings(tmp_path, "expected", tmp_path / "no-serial", tmp_path / "no-usb")
    client = create_app(settings=config, camera=FakeCamera()).test_client()
    assert client.post("/api/camera/start").status_code == 403
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control": token}
    assert client.post("/api/control/take").status_code == 423
    assert client.post("/api/camera/start", headers=headers).status_code == 202
    assert client.post("/api/camera/settings", headers=headers, json={"gain": "bad", "exposure_us": 100000}).status_code == 400
    assert client.post("/api/control/release", headers=headers).status_code == 200
    assert client.post("/api/camera/stop", headers=headers).status_code == 403


def test_worker_input_validation_without_sdk():
    worker = CameraWorker()
    for gain, exposure in [(101, 100_000), (0, -1), ("0", 100_000)]:
        try:
            worker.configure(gain, exposure)
        except ValueError:
            pass
        else:
            raise AssertionError("Accepted invalid camera settings")


def test_worker_initializes_exposure_before_gain():
    import threading
    import time
    from astropi.camera.sdk import GAIN, EXPOSURE

    events = []
    running = threading.Event()

    class OrderedDriver:
        def open(self):
            events.append("open")
        def set_control(self, control, value):
            events.append(("control", control, value))
            return value
        def start(self):
            events.append("start")
            running.set()
        def get_frame(self, buffer, wait_ms):
            time.sleep(0.01)
        def close(self):
            events.append("close")

    worker = CameraWorker(driver_factory=OrderedDriver)
    assert worker.start()
    assert running.wait(timeout=3)
    assert worker.stop()
    worker._thread.join(timeout=3)
    assert not worker._thread.is_alive()
    controls = [ev[1] for ev in events if isinstance(ev, tuple)]
    assert controls[:2] == [EXPOSURE, GAIN]
    assert worker.status()["phase"] == "stopped"


def test_worker_setting_command_is_acknowledged_only_when_applied(monkeypatch):
    import threading
    import time
    from astropi.camera import worker as module
    from astropi.camera.sdk import EXPOSURE, GAIN

    monkeypatch.setattr(module, "raw16_to_jpeg", lambda raw, stretch="auto": b"\xff\xd8test")
    active = threading.Event()
    observed = []

    class FakeDriver:
        def open(self):
            pass
        def set_control(self, control, value):
            observed.append((control, value))
            return value
        def start(self):
            active.set()
        def get_frame(self, raw, wait_ms):
            time.sleep(0.01)
        def close(self):
            pass

    worker = CameraWorker(driver_factory=FakeDriver)
    assert worker.start()
    assert active.wait(timeout=3)
    id1 = worker.configure(25, 200_000)
    assert id1 == 1
    deadline = time.monotonic() + 3
    while worker.status()["settings_applied_id"] < id1 and time.monotonic() < deadline:
        time.sleep(0.01)
    state = worker.status()
    assert state["settings_applied_id"] == id1
    assert state["gain"] == 25
    assert state["exposure_us"] == 200_000
    assert observed[-2:] == [(EXPOSURE, 200_000), (GAIN, 25)]
    worker.stop()
    worker._thread.join(timeout=3)
    assert not worker._thread.is_alive()


def test_fast_camera_progress_endpoint_works(tmp_path):
    config = Settings(tmp_path, "expected", tmp_path / "serial", tmp_path / "usb")
    client = create_app(settings=config, camera=FakeCamera()).test_client()
    response = client.get("/api/camera/progress")
    assert response.status_code == 200
    assert response.get_json()["frame_number"] == 0



def test_gain_changes_unstretched_pixels_even_if_auto_preview_looks_similar():
    import numpy as np
    raw = np.empty((HEIGHT, WIDTH), dtype="<u2")
    raw[:] = 144 << 4
    fixed_low = np.asarray(Image.open(io.BytesIO(raw16_to_jpeg(raw, stretch="fixed"))))
    auto_low = np.asarray(Image.open(io.BytesIO(raw16_to_jpeg(raw, stretch="auto"))))
    stats_low = raw16_statistics(raw)
    raw[:] = 550 << 4
    fixed_high = np.asarray(Image.open(io.BytesIO(raw16_to_jpeg(raw, stretch="fixed"))))
    auto_high = np.asarray(Image.open(io.BytesIO(raw16_to_jpeg(raw, stretch="auto"))))
    stats_high = raw16_statistics(raw)
    assert stats_low["raw_mean_adu"] == 144
    assert stats_high["raw_mean_adu"] == 550
    assert float(fixed_high.mean()) > float(fixed_low.mean()) + 25
    # Constant uniform scenes have the same output under auto normalization.
    assert abs(float(auto_high.mean()) - float(auto_low.mean())) < 2


def test_preview_mode_endpoint_requires_operator(tmp_path):
    config = Settings(tmp_path, "expected", tmp_path / "serial", tmp_path / "usb")
    client = create_app(settings=config, camera=FakeCamera()).test_client()
    assert client.post("/api/camera/preview-mode", json={"mode": "fixed"}).status_code == 403
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control": token}
    response = client.post("/api/camera/preview-mode", headers=headers, json={"mode": "fixed"})
    assert response.status_code == 200
    assert response.get_json()["mode"] == "fixed"
    assert client.post("/api/camera/preview-mode", headers=headers, json={"mode": "invalid"}).status_code == 400


def test_preview_statistics_reject_short_buffer():
    try:
        raw16_statistics(bytes(2))
    except ValueError:
        pass
    else:
        raise AssertionError("Short raw buffer accepted")



def test_exposure_presets_and_long_exposure_wait_time():
    from astropi.camera.worker import EXPOSURE_PRESETS_US, frame_wait_ms
    assert len(EXPOSURE_PRESETS_US) == 18
    assert EXPOSURE_PRESETS_US[0] == 1_000
    assert EXPOSURE_PRESETS_US[-1] == 30_000_000
    assert frame_wait_ms(1_000) >= 2_500
    assert frame_wait_ms(30_000_000) >= 34_000

    worker = CameraWorker()
    worker._phase = "running"
    for duration in EXPOSURE_PRESETS_US:
        assert isinstance(worker.configure(0, duration), int)
        # The hardware worker normally drains the bounded queue; simulate it here.
        worker._commands.get_nowait()

    for invalid in (999, 1_500, 35_000_000, 500_000.0, "1000", True):
        try:
            worker.configure(0, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid exposure preset accepted: {invalid!r}")
