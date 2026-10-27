"""Real disk/format tests run on a temporary filesystem, NEVER actual camera/USB."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import time

import numpy as np
import pytest
from PIL import Image

from astropi.camera.sdk import WIDTH, HEIGHT, RAW_BYTES
from astropi.capture.formats import (
    FORMATS, fits_bytes, quicklook_bytes, quicklook_image, validate_formats,
)
from astropi.capture.manager import CaptureManager, CaptureBusy
from astropi.capture.storage import CaptureStorage, StorageError
from astropi.config import Settings
from astropi.web import create_app

WHEN = datetime(2026, 10, 27, 20, 30, 0, tzinfo=timezone.utc)


def sample_raw():
    image = np.full((HEIGHT, WIDTH), 180 << 4, dtype="<u2")
    image[0, 0] = 0
    image[0, 1] = 4095 << 4
    image[1, 0] = 1000 << 4
    image[1, 1] = 2000 << 4
    return image.tobytes()


def settings(tmp_path):
    return Settings(
        storage_mount=tmp_path, storage_uuid="mocked-uuid",
        mount_serial=tmp_path / "serial", usb_sysfs=tmp_path / "usb",
    )


def verified_storage(tmp_path):
    return CaptureStorage(
        settings(tmp_path),
        verifier=lambda path, uuid: {
            "ready": True, "free_bytes": 1_000_000_000, "state": "ready",
        },
    )


def test_format_validation():
    assert validate_formats(["png", "fits", "raw"]) == ("raw", "fits", "png")
    for bad in ([], None, "fits", ["gif"], ["fits", "fits"], ["jpg", 3]):
        with pytest.raises(ValueError):
            validate_formats(bad)


def test_fits_unsigned_bayer_and_padding():
    raw = sample_raw()
    fits = fits_bytes(raw, exposure_us=100_000, gain=30, received_at=WHEN)
    header_end = fits.find(b"END".ljust(80)) + 80
    header_len = (header_end + 2879) // 2880 * 2880
    hdr = fits[:header_len]
    assert hdr.startswith(b"SIMPLE  =")
    for key in (b"BITPIX", b"NAXIS1", b"NAXIS2", b"BZERO", b"BSCALE",
                b"BAYERPAT", b"EXPTIME", b"DATE-OBS", b"TIMEQUAL"):
        assert key in hdr
    assert b"'GRBG'" in hdr
    assert b"ESTIMATED" in hdr
    assert len(fits) % 2880 == 0
    data = np.frombuffer(fits, dtype=">i2", offset=header_len, count=WIDTH * HEIGHT)
    physical = data[:4].astype(np.int32) + 32768
    assert physical.tolist() == [0, 4095, 180, 180]
    assert len(raw) == RAW_BYTES


def test_full_capture_all_formats_and_checksums(tmp_path):
    raw = sample_raw()
    result = verified_storage(tmp_path).save(
        raw, FORMATS, gain=30, exposure_us=100_000,
        received_at=WHEN, stretch="fixed",
    )
    shot = tmp_path / result["directory"]
    assert shot.is_dir()
    assert len(result["files"]) == 4
    metadata = json.loads((shot / "metadata.json").read_text())
    assert metadata["native_left_shift"] == 4
    assert metadata["time_received_utc"] == WHEN.isoformat()
    assert metadata["quicklook_dimensions"] == [1928, 1090]
    assert (shot / "sv705c.raw16").read_bytes() == raw
    for entry in result["files"]:
        data = (tmp_path / entry["path"]).read_bytes()
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert entry["bytes"] == len(data)
    assert (shot / "sv705c.fits").stat().st_size % 2880 == 0
    assert Image.open(shot / "sv705c.jpg").size == (WIDTH // 2, HEIGHT // 2)
    assert Image.open(shot / "sv705c.png").size == (WIDTH // 2, HEIGHT // 2)
    assert Image.open(shot / "sv705c.png").mode == "RGB"
    assert not list(tmp_path.rglob("*.partial"))


def test_usb_drive_must_be_exact_verified_mount(tmp_path):
    store = CaptureStorage(settings(tmp_path))
    with pytest.raises(StorageError, match="Recording refused"):
        store.preflight(("fits",))
    assert list(tmp_path.iterdir()) == []
    false_uuid = CaptureStorage(settings(tmp_path), verifier=lambda path, uuid: {
        "ready": False, "state": "wrong_or_unknown_uuid", "free_bytes": 1000000000,
    })
    with pytest.raises(StorageError, match="wrong_or_unknown_uuid"):
        false_uuid.save(sample_raw(), ("raw",), gain=0, exposure_us=100000,
                        received_at=WHEN, stretch="auto")
    assert list(tmp_path.iterdir()) == []


def test_low_space_rejected_before_creating_files(tmp_path):
    storage = CaptureStorage(settings(tmp_path), verifier=lambda path, uuid: {
        "ready": True, "state": "ready", "free_bytes": 1024,
    })
    with pytest.raises(StorageError, match="insufficient USB space"):
        storage.preflight(("raw", "fits"))
    assert not (tmp_path / "captures").exists()


class FakeSave:
    def __init__(self):
        self.received = []
    def preflight(self, formats):
        return {"ready": True}
    def save(self, raw, formats, **kw):
        self.received.append((raw, formats, kw))
        return {"directory": "captures/mock", "files": [{"format":"FITS","path":"captures/mock/s.fits","bytes":3}],
                "total_bytes": 3}


def test_capture_manager_consumes_one_frame_and_finishes():
    save = FakeSave()
    manager = CaptureManager(save)
    identifier = manager.request(["fits", "jpg"])
    assert manager.status()["phase"] == "waiting"
    with pytest.raises(CaptureBusy):
        manager.request(["fits"])
    assert manager.accept_frame(b"first-raw", gain=20, exposure_us=100_000,
                                stretch="auto") is True
    assert manager.accept_frame(b"second", gain=20, exposure_us=100_000,
                                stretch="auto") is False
    limit = time.monotonic() + 3
    while manager.status()["phase"] == "saving" and time.monotonic() < limit:
        time.sleep(0.01)
    status = manager.status()
    assert status["phase"] == "done"
    assert status["id"] == identifier
    assert save.received[0][0] == b"first-raw"
    assert save.received[0][1] == ("fits", "jpg")
    assert status["total_bytes"] == 3
    assert manager.request(["raw"]) != identifier


def test_capture_cancelled_on_camera_stop_before_frame():
    manager = CaptureManager(FakeSave())
    manager.request(["raw"])
    manager.fail_waiting("Camera stopped")
    assert manager.status()["phase"] == "error"
    assert not manager.accept_frame(b"old", gain=0, exposure_us=100000, stretch="fixed")


class FakeCaptureCamera:
    def status(self):
        return {"phase": "running", "gain": 0, "exposure_us": 100000,
                "settings_applied_id": 0, "frame_number": 0, "has_frame": False}
    def capture_status(self):
        return {"phase": "idle", "files": []}
    def request_capture(self, formats):
        if formats == ["fits"]:
            return "test-capture-id"
        raise StorageError("Recording refused: USB drive not mounted")


def test_capture_api_requires_operator_and_valid_formats(tmp_path):
    client = create_app(settings=settings(tmp_path), camera=FakeCaptureCamera()).test_client()
    assert client.post("/api/capture", json={"formats": ["fits"]}).status_code == 403
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control": token}
    assert client.post("/api/capture", headers=headers, json={"formats": []}).status_code == 400
    r = client.post("/api/capture", headers=headers, json={"formats": ["fits"]})
    assert r.status_code == 202
    assert r.get_json()["id"] == "test-capture-id"
    assert client.post("/api/capture", headers=headers, json={"formats": ["png"]}).status_code == 503
    assert client.get("/api/capture/status").get_json()["phase"] == "idle"



def test_mid_save_failure_leaves_only_an_explicitly_partial_capture(tmp_path):
    class FailSecondFile(CaptureStorage):
        def _atomic_write(self, dir_fd, name, payload):
            if name == "sv705c.fits":
                raise OSError("simulated disk write failure")
            return super()._atomic_write(dir_fd, name, payload)

    store = FailSecondFile(
        settings(tmp_path),
        verifier=lambda path, uuid: {
            "ready": True, "free_bytes": 1_000_000_000, "state": "ready",
        },
    )
    with pytest.raises(OSError, match="simulated disk write failure"):
        store.save(sample_raw(), ("raw", "fits"), gain=0, exposure_us=100_000,
                   received_at=WHEN, stretch="fixed")
    recorded = list((tmp_path / "captures").iterdir())
    assert len(recorded) == 1
    assert recorded[0].name.endswith(".partial")
    assert not (recorded[0] / "metadata.json").exists()
    assert (recorded[0] / "sv705c.raw16").exists()
    assert not (recorded[0] / "sv705c.fits").exists()
