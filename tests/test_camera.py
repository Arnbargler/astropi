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
    def set_debayer(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Debayer must be boolean")
        return enabled
    def set_binning(self, binning):
        if type(binning) is not int or binning not in (1, 2):
            raise ValueError("Invalid binning")
        return binning
    def capture_status(self):
        return {"phase": "idle", "id": None, "files": []}
    def request_capture(self, formats):
        return "fake-id"


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

    monkeypatch.setattr(module, "raw16_to_jpeg",
                        lambda raw, stretch="auto", debayer=True: b"\xff\xd8test")
    monkeypatch.setattr(module, "raw16_statistics",
                        lambda raw: dict(raw_mean_adu=100, raw_p99_adu=200,
                                         raw_saturated_percent=0))
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
    id1 = worker.configure(30, 250_000)
    assert id1 == 1
    deadline = time.monotonic() + 3
    while worker.status()["settings_applied_id"] < id1 and time.monotonic() < deadline:
        time.sleep(0.01)
    state = worker.status()
    assert state["settings_applied_id"] == id1
    assert state["gain"] == 30
    assert state["exposure_us"] == 250_000
    assert observed[-2:] == [(EXPOSURE, 250_000), (GAIN, 30)]
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
        assert worker._pending_settings[2] == duration

    for invalid in (999, 1_500, 35_000_000, 500_000.0, "1000", True):
        try:
            worker.configure(0, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid exposure preset accepted: {invalid!r}")



def test_monochrome_preview_is_grayscale_and_does_not_mutate_RAW():
    pixels = np.empty((HEIGHT, WIDTH), dtype="<u2")
    pixels[0::2, 0::2] = 1200 << 4
    pixels[0::2, 1::2] = 3000 << 4
    pixels[1::2, 0::2] = 900 << 4
    pixels[1::2, 1::2] = 1600 << 4
    before = pixels.copy()
    for stretch in ("auto", "fixed"):
        mono = Image.open(io.BytesIO(raw16_to_jpeg(pixels, stretch=stretch, debayer=False)))
        colour = Image.open(io.BytesIO(raw16_to_jpeg(pixels, stretch=stretch, debayer=True)))
        assert mono.mode == "L"
        assert colour.mode == "RGB"
        assert mono.size == colour.size == (WIDTH // 4, HEIGHT // 4)
    assert np.array_equal(before, pixels)


def test_backend_debayer_selection_requires_operator(tmp_path):
    config = Settings(tmp_path, "expected", tmp_path / "missing-serial", tmp_path / "missing-usb")
    client = create_app(settings=config, camera=FakeCamera()).test_client()
    assert client.post("/api/camera/debayer", json={"enabled": False}).status_code == 403
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control": token}
    assert client.post("/api/camera/debayer", headers=headers,
                       json={"enabled": False}).get_json()["enabled"] is False
    assert client.post("/api/camera/debayer", headers=headers,
                       json={"enabled": "false"}).status_code == 400


def test_rapid_preset_clicks_coalesce_to_latest_request():
    from astropi.camera.worker import GAIN_PRESETS
    assert GAIN_PRESETS == (0, 5, 10, 20, 30, 50, 75, 100)
    worker = CameraWorker()
    worker._phase = "running"
    for i, gain in enumerate(GAIN_PRESETS, start=1):
        assert worker.configure(gain, 100_000) == i
    assert worker._pending_settings == (len(GAIN_PRESETS), 100, 100_000)
    assert worker.status()["settings_applied_id"] == 0
    assert worker.set_debayer(False) is False
    assert worker.status()["debayer"] is False
    for invalid in (0, "off", None):
        try:
            worker.set_debayer(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Nonboolean debayer was accepted")



def test_binning_geometry_is_sensor_documented_1x_2x_only():
    from astropi.camera.sdk import frame_dimensions, frame_bytes, SUPPORTED_BINNING
    assert SUPPORTED_BINNING == (1, 2)
    assert frame_dimensions(1) == (3856, 2180)
    assert frame_dimensions(2) == (1928, 1090)
    assert frame_bytes(1) == RAW_BYTES
    assert frame_bytes(2) == 4_203_520
    for bad in (0, 3, 4, None, "2", 2.0, True):
        with __import__("pytest").raises(ValueError):
            frame_dimensions(bad)


def test_binned_preview_monochrome_correct_dimensions_and_preserves_source():
    raw = np.full((HEIGHT // 2, WIDTH // 2), 384 << 4, dtype="<u2")
    before = raw.copy()
    for debayer in (True, False):
        jpeg = raw16_to_jpeg(raw, stretch="fixed", debayer=debayer, binning=2)
        image = Image.open(io.BytesIO(jpeg))
        assert image.mode == "L"
        assert image.size == (WIDTH // 4, HEIGHT // 4)
    assert raw16_statistics(raw, binning=2)["raw_mean_adu"] == 384
    assert np.array_equal(raw, before)
    with __import__("pytest").raises(ValueError):
        raw16_to_jpeg(raw, binning=1)


def test_binning_endpoint_requires_lease_and_whitelisted_levels(tmp_path):
    config = Settings(tmp_path, "expected", tmp_path / "serial", tmp_path / "usb")
    client = create_app(settings=config, camera=FakeCamera()).test_client()
    assert client.post("/api/camera/binning", json={"binning":2}).status_code == 403
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control": token}
    for bad in (3, 4, 0, None, True, "2"):
        assert client.post("/api/camera/binning", json={"binning":bad},
                           headers=headers).status_code == 400
    assert client.post("/api/camera/binning", json={"binning":2},
                       headers=headers).get_json()["binning"] == 2


def test_worker_switches_binning_by_closing_and_reopening_sdk_session(monkeypatch):
    import threading
    import time
    from astropi.camera import worker as module
    from astropi.camera.sdk import frame_bytes

    monkeypatch.setattr(module,"raw16_to_jpeg",lambda *args,**kwargs:b"\xff\xd8preview")
    monkeypatch.setattr(module,"raw16_statistics",lambda *args,**kwargs:{
        "raw_mean_adu":10.0,"raw_p99_adu":20,"raw_saturated_percent":0.0})
    events=[]
    sessions=[]
    class Driver:
        def __init__(self):
            self.index=len(sessions)
            sessions.append(self)
        def open(self):
            events.append((self.index,"open"))
        def configure_binning(self, binning):
            events.append((self.index,"bin",binning))
        def set_control(self,control,value):
            return value
        def start(self):
            events.append((self.index,"start"))
        def get_frame(self,buffer,wait_ms):
            time.sleep(0.01)
        def close(self):
            events.append((self.index,"close"))

    worker=CameraWorker(driver_factory=Driver)
    assert worker.start()
    deadline=time.monotonic()+4
    while worker.status()["phase"]!="running" and time.monotonic()<deadline:
        time.sleep(.01)
    assert worker.status()["phase"]=="running"
    assert worker.set_binning(2)==2
    deadline=time.monotonic()+5
    while not (len(sessions)>=2 and worker.status()["phase"]=="running") and time.monotonic()<deadline:
        time.sleep(.01)
    assert worker.status()["phase"]=="running"
    assert worker.status()["binning"]==2
    assert worker.status()["width"]==1928
    assert worker.status()["height"]==1090
    assert events.index((0,"close")) < events.index((1,"open"))
    assert (1,"bin",2) in events
    assert worker.set_binning(1)==1
    deadline=time.monotonic()+5
    while not (len(sessions)>=3 and worker.status()["phase"]=="running") and time.monotonic()<deadline:
        time.sleep(.01)
    assert worker.status()["binning"]==1
    assert worker.status()["phase"]=="running"
    assert (2,"bin",2) not in events
    worker.stop()
    worker._thread.join(timeout=4)
    assert not worker._thread.is_alive()


def test_change_binning_rejected_during_capture():
    import pytest
    from astropi.camera.worker import CameraWorker
    class BusyCapture:
        def status(self):
            return {"phase":"saving"}
    worker=CameraWorker(capture=BusyCapture())
    worker._phase="running"
    with pytest.raises(RuntimeError,match="capture"):
        worker.set_binning(2)
    assert worker.status()["binning"]==1
    for bad in (3,4,"2"):
        with pytest.raises(ValueError):
            worker.set_binning(bad)
