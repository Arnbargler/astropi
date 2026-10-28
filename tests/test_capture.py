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
    def preflight(self, formats, *, count=1):
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
    def cancel_capture(self):
        return "sequence-id"
    def request_capture(self, formats, count=1):
        if formats == ["fits"]:
            return "test-capture-id"
        if formats == ["raw"] and count in (4, 200):
            return "sequence-id"
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



def test_sequence_saves_each_frame_and_reports_progress():
    import threading

    class ControlledSave(FakeSave):
        def __init__(self):
            super().__init__()
            self.started = threading.Event()
            self.finish = threading.Event()
            self.preflight_count = None
        def preflight(self, formats, *, count=1):
            self.preflight_count = count
        def save(self, raw, formats, **kw):
            self.started.set()
            if not self.finish.wait(timeout=3):
                raise RuntimeError("test writer timeout")
            return super().save(raw, formats, **kw)

    store = ControlledSave()
    manager = CaptureManager(store)
    identifier = manager.request(["fits"], count=3)
    assert store.preflight_count == 3
    assert manager.status()["total_frames"] == 3
    assert manager.accept_frame(b"shot1", gain=10, exposure_us=100_000,
                                stretch="fixed")
    assert store.started.wait(3)
    assert manager.status()["phase"] == "saving"
    assert not manager.accept_frame(b"duplicate", gain=10, exposure_us=100_000,
                                    stretch="fixed")
    with pytest.raises(CaptureBusy):
        manager.request(["fits"])
    store.finish.set()
    deadline = time.monotonic() + 3
    while manager.status()["completed_frames"] < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert manager.status()["completed_frames"] == 1
    for i in (2, 3):
        assert manager.accept_frame(f"shot{i}".encode(), gain=10,
                                    exposure_us=100_000, stretch="fixed")
        deadline = time.monotonic() + 3
        while manager.status()["completed_frames"] < i and time.monotonic() < deadline:
            time.sleep(0.01)
    state = manager.status()
    assert state["phase"] == "done"
    assert state["completed_frames"] == state["total_frames"] == 3
    assert len(store.received) == 3
    assert [x[0] for x in store.received] == [b"shot1", b"shot2", b"shot3"]
    assert [x[2]["sequence"]["index"] for x in store.received] == [1, 2, 3]
    assert all(x[2]["sequence"]["id"] == identifier for x in store.received)


def test_sequence_can_cancel_between_frames():
    manager = CaptureManager(FakeSave())
    manager.request(["fits"], count=10)
    assert manager.cancel() == manager.status()["id"]
    assert manager.status()["phase"] == "cancelled"
    assert manager.status()["completed_frames"] == 0
    assert not manager.accept_frame(b"unwanted", gain=0, exposure_us=100000, stretch="auto")


def test_sequence_cancellation_finishes_inflight_write():
    import threading
    class ControlledSave(FakeSave):
        def __init__(self):
            super().__init__()
            self.started = threading.Event()
            self.finish = threading.Event()
        def save(self, raw, formats, **kw):
            self.started.set()
            self.finish.wait(3)
            return super().save(raw, formats, **kw)

    store = ControlledSave()
    manager = CaptureManager(store)
    manager.request(["fits"], count=5)
    assert manager.accept_frame(b"first", gain=0, exposure_us=100000, stretch="auto")
    assert store.started.wait(3)
    manager.cancel()
    assert manager.status()["phase"] == "saving"
    assert manager.status()["cancel_requested"]
    store.finish.set()
    deadline = time.monotonic() + 3
    while manager.status()["phase"] == "saving" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert manager.status()["phase"] == "cancelled"
    assert manager.status()["completed_frames"] == 1
    assert not manager.accept_frame(b"second", gain=0, exposure_us=100000, stretch="auto")


def test_sequence_storage_space_reservation_and_limit(tmp_path):
    store = verified_storage(tmp_path)
    assert store.preflight(("fits",), count=25)["ready"]
    with pytest.raises(StorageError, match="insufficient USB space"):
        store.preflight(("raw", "fits", "jpg", "png"), count=100)
    manager = CaptureManager(FakeSave())
    assert manager.MAX_FRAMES == 200
    for value in (0, -1, 201, 1.5, "10", True):
        with pytest.raises(ValueError):
            manager.request(["fits"], count=value)


def test_sequence_stop_before_frame_reports_failure():
    manager = CaptureManager(FakeSave())
    manager.request(["fits"], count=10)
    manager.fail_waiting("Camera stopped during sequence")
    assert manager.status()["phase"] == "error"
    assert "stopped" in manager.status()["error"]


def test_sequence_http_lease_and_cancel(tmp_path):
    camera = FakeCaptureCamera()
    client = create_app(settings=settings(tmp_path), camera=camera).test_client()
    assert client.post("/api/capture/sequence", json={"formats":["raw"],"count":4}).status_code == 403
    token = client.post("/api/control/take").get_json()["token"]
    headers = {"X-AstroPi-Control":token}
    for bad in (0,1,201,"4",True):
        assert client.post("/api/capture/sequence", headers=headers,
                           json={"formats":["fits"],"count":bad}).status_code == 400
    response=client.post("/api/capture/sequence", headers=headers,
                         json={"formats":["raw"],"count":4})
    assert response.status_code == 202
    assert response.get_json()["id"] == "sequence-id"
    long_run=client.post("/api/capture/sequence",headers=headers,
                         json={"formats":["raw"],"count":200})
    assert long_run.status_code == 202
    assert long_run.get_json()["count"] == 200
    assert client.post("/api/capture/cancel").status_code == 403
    assert client.post("/api/capture/cancel", headers=headers).status_code == 202


def test_sequence_metadata_is_recorded_in_each_frame(tmp_path):
    raw=sample_raw()
    store=verified_storage(tmp_path)
    save=store.save(raw,("fits",),gain=30,exposure_us=100000,received_at=WHEN,
        stretch="auto",sequence={"id":"sequence123","index":1,"count":5})
    manifest=json.loads((tmp_path / save["directory"] / "metadata.json").read_text())
    assert manifest["sequence"] == {"id":"sequence123","index":1,"count":5}



def test_independent_read_only_fits_and_raw16_verifier(tmp_path):
    from astropi.capture.verify import check_capture
    raw = sample_raw()
    result = verified_storage(tmp_path).save(
        raw, ("raw", "fits"), gain=0, exposure_us=100000,
        stretch="fixed", received_at=WHEN,
    )
    folder = tmp_path / result["directory"]
    outcome = check_capture(folder)
    assert outcome["files"] == 2
    assert outcome["fits_checked"]
    assert outcome["raw_pixels_equal"]
    # Corrupt the scientific FITS pixel data: metadata hash must fail.
    with (folder / "sv705c.fits").open("r+b") as handle:
        handle.seek(-100, os.SEEK_END)
        handle.write(b"\x08")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        check_capture(folder)


def test_capture_worker_freezes_gain_exposure_during_active_sequence():
    from astropi.camera.worker import CameraWorker
    import threading

    class NoDisk:
        def __init__(self):
            self.active = True
        def active_sequence(self):
            return self.active

    worker = CameraWorker(capture=NoDisk())
    worker._phase = "running"
    with pytest.raises(RuntimeError, match="locked"):
        worker.configure(10, 100_000)
    assert worker._settings_request_id == 0



def test_sequence_quicklook_stretch_frozen_at_start():
    store = FakeSave()
    manager = CaptureManager(store)
    manager.request(["jpg"], count=2, stretch="fixed")
    assert manager.accept_frame(b"one", gain=0, exposure_us=100000,
                                stretch="auto")
    deadline = time.monotonic() + 3
    while manager.status()["completed_frames"] < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert manager.accept_frame(b"two", gain=0, exposure_us=100000,
                                stretch="auto")
    deadline = time.monotonic() + 3
    while manager.status()["phase"] == "saving" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert manager.status()["phase"] == "done"
    assert [x[2]["stretch"] for x in store.received] == ["fixed", "fixed"]



def test_2x2_binning_writes_correct_raw_fits_and_colour_quicklooks(tmp_path):
    from astropi.capture.verify import check_capture
    from astropi.camera.sdk import frame_bytes
    raw = np.full((HEIGHT // 2, WIDTH // 2), 400 << 4, dtype="<u2")
    raw[0, 0] = 0
    raw[0, 1] = 4095 << 4
    assert raw.nbytes == frame_bytes(2)
    result = verified_storage(tmp_path).save(
        raw.tobytes(), FORMATS, gain=30, exposure_us=100_000,
        received_at=WHEN, stretch="fixed", binning=2
    )
    folder = tmp_path / result["directory"]
    manifest = json.loads((folder / "metadata.json").read_text())
    assert manifest["binning"] == 2
    assert manifest["width"] == 1928
    assert manifest["height"] == 1090
    assert manifest["bayer"] == "unverified at 2x2"
    assert manifest["quicklook_dimensions"] == [964, 545]
    assert (folder / "sv705c.raw16").read_bytes() == raw.tobytes()
    for kind in ("jpg", "png"):
        quicklook = Image.open(folder / ("sv705c." + kind))
        assert quicklook.mode == "RGB"
        assert quicklook.size == (964, 545)
    assert manifest["quicklook_debayer"] is True
    fits = (folder / "sv705c.fits").read_bytes()
    assert b"XBINNING" in fits[:2880]
    assert b"YBINNING" in fits[:2880]
    assert b"BAYERPAT" not in fits[:2880]
    assert check_capture(folder)["raw_pixels_equal"] is True
    assert not list(tmp_path.rglob("*.partial"))


def test_binning_2_does_not_accept_full_resolution_input(tmp_path):
    with pytest.raises(StorageError,match="Wrong RAW16 size"):
        verified_storage(tmp_path).save(
            sample_raw(), ("raw",), gain=0, exposure_us=100_000,
            received_at=WHEN, stretch="auto", binning=2
        )
    assert not (tmp_path / "captures").exists()



def test_capture_manager_preserves_binning_through_async_save():
    fake = FakeSave()
    manager = CaptureManager(fake)
    manager.request(["raw", "fits"])
    assert manager.accept_frame(b"binned-frame", gain=10, exposure_us=250_000,
                                stretch="fixed", binning=2)
    deadline = time.monotonic() + 3
    while manager.status()["phase"] == "saving" and time.monotonic() < deadline:
        time.sleep(.01)
    assert manager.status()["phase"] == "done"
    assert fake.received[0][0] == b"binned-frame"
    assert fake.received[0][2]["binning"] == 2



def test_binned_debayer_off_saves_monochrome_jpg_png_and_original_science(tmp_path):
    from astropi.capture.verify import check_capture
    raw = np.full((HEIGHT // 2, WIDTH // 2), 1024 << 4, dtype="<u2").tobytes()
    for binning, pixels in ((2, raw), (1, sample_raw())):
        result = verified_storage(tmp_path).save(
            pixels, FORMATS, gain=20, exposure_us=50_000,
            received_at=WHEN, stretch="fixed", binning=binning, debayer=False
        )
        folder = tmp_path / result["directory"]
        metadata = json.loads((folder / "metadata.json").read_text())
        assert metadata["quicklook_debayer"] is False
        assert metadata["binning"] == binning
        assert (folder / "sv705c.raw16").read_bytes() == pixels
        assert check_capture(folder)["raw_pixels_equal"] is True
        for fmt in ("jpg", "png"):
            image = Image.open(folder / ("sv705c." + fmt))
            assert image.mode == "L"
            assert image.size == (metadata["width"] // 2, metadata["height"] // 2)


def test_capture_sequence_freezes_binning_colour_choice():
    store = FakeSave()
    manager = CaptureManager(store)
    manager.request(["jpg"], count=2, debayer=False)
    for i in range(2):
        assert manager.accept_frame(f"shot{i}".encode(), gain=0, exposure_us=100000,
                                    stretch="auto", binning=2)
        deadline = time.monotonic() + 3
        while manager.status()["phase"] == "saving" and time.monotonic() < deadline:
            time.sleep(0.01)
    assert manager.status()["phase"] == "done"
    assert [record[2]["debayer"] for record in store.received] == [False, False]


def test_reject_nonboolean_debayer_capture_options(tmp_path):
    for invalid in (None, 0, "off", 1, []):
        with pytest.raises(ValueError, match="Debayer"):
            quicklook_image(sample_raw(), debayer=invalid)
        with pytest.raises(ValueError, match="Debayer"):
            CaptureManager(FakeSave()).request(["jpg"], debayer=invalid)


def test_max_sequence_200_saves_incrementally_and_can_be_cancelled():
    manager=CaptureManager(FakeSave())
    job=manager.request(["raw"],count=200)
    assert job == manager.status()["id"]
    assert manager.status()["total_frames"] == 200
    assert manager.active_sequence()
    assert manager.accept_frame(b"frame",gain=0,exposure_us=100_000,stretch="fixed")
    import time
    until=time.monotonic()+3
    while manager.status()["phase"]=="saving" and time.monotonic()<until:
        time.sleep(0.01)
    assert manager.status()["completed_frames"] == 1
    assert manager.cancel() == job
    assert manager.status()["phase"] == "cancelled"
    assert manager.status()["completed_frames"] == 1
    assert not manager.accept_frame(b"other",gain=0,exposure_us=100_000,stretch="fixed")
