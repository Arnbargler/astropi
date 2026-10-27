import io
import numpy as np
from PIL import Image

from astropi.camera.preview import raw16_to_jpeg
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
