"""Sole SDK worker for RAW acquisition, separate bounded JPEG preview consumer.

Only the acquisition thread touches SVBONY's SDK. The JPEG worker receives
immutable copies of the newest available full RAW16 frames via a one-slot
mailbox. When processing lags acquisition, frames are dropped, not queued.
"""
import ctypes as C
from queue import Empty, Full, Queue
import threading
import time

from .sdk import SVBDriver, SDKError, RAW_BYTES, GAIN, EXPOSURE
from .preview import raw16_to_jpeg, raw16_statistics


EXPOSURE_PRESETS_US = (
    1_000, 2_000, 5_000, 10_000, 25_000, 50_000, 100_000,
    250_000, 500_000, 750_000, 1_000_000, 2_000_000,
    5_000_000, 10_000_000, 15_000_000, 20_000_000,
    25_000_000, 30_000_000,
)
GAIN_PRESETS = (0, 5, 10, 20, 30, 50, 75, 100)


def frame_wait_ms(exposure_us):
    """Allow SDK frame wait to span an exposure plus transfer margin."""
    return max(2_500, exposure_us // 1_000 + 4_000)


class CameraWorker:
    def __init__(self, driver_factory=SVBDriver):
        self._driver_factory = driver_factory
        self._lock = threading.Lock()
        self._thread = None
        self._preview_thread = None
        self._stop = threading.Event()
        self._pending_settings = None
        self._raw_mailbox = Queue(maxsize=1)
        self._phase = "stopped"
        self._error = None
        self._preview_error = None
        self._image = None
        self._sequence = 0
        self._gain = 0
        self._exposure_us = 100_000
        self._settings_request_id = 0
        self._settings_applied_id = 0
        self._capture_fps = 0.0
        self._preview_fps = 0.0
        self._preview_ms = 0.0
        self._preview_mode = "auto"
        self._debayer = True
        self._raw_mean_adu = None
        self._raw_p99_adu = None
        self._raw_saturated_percent = None

    def status(self):
        with self._lock:
            return {
                "phase": self._phase, "last_error": self._error,
                "frame_number": self._sequence, "has_frame": self._image is not None,
                "gain": self._gain, "exposure_us": self._exposure_us,
                "settings_applied_id": self._settings_applied_id,
                "capture_fps": self._capture_fps,
                "preview_fps": self._preview_fps,
                "preview_processing_ms": self._preview_ms,
                "preview_mode": self._preview_mode, "debayer": self._debayer,
                "raw_mean_adu": self._raw_mean_adu,
                "raw_p99_adu": self._raw_p99_adu,
                "raw_saturated_percent": self._raw_saturated_percent,
            }

    def frame(self):
        with self._lock:
            return self._image, self._sequence

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop = threading.Event()
            self._raw_mailbox = Queue(maxsize=1)
            self._pending_settings = None
            self._phase = "connecting"
            self._error = self._preview_error = None
            self._image = None
            self._sequence = 0
            self._settings_request_id = self._settings_applied_id = 0
            self._capture_fps = self._preview_fps = self._preview_ms = 0.0
            self._raw_mean_adu = None
            self._raw_p99_adu = None
            self._raw_saturated_percent = None
            self._thread = threading.Thread(target=self._run, name="sv705c-sdk", daemon=True)
            self._thread.start()
            return True

    def stop(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return False
            self._phase = "stopping"
            self._stop.set()
            return True

    def configure(self, gain, exposure_us):
        if type(gain) is not int or gain not in GAIN_PRESETS:
            raise ValueError("Gain must be a selected preset (0, 5, 10, 20, 30, 50, 75, 100)")
        if type(exposure_us) is not int or exposure_us not in EXPOSURE_PRESETS_US:
            raise ValueError("Exposure must be a selected preset (1 ms to 30 s)")
        with self._lock:
            if self._phase not in ("connecting", "running"):
                raise RuntimeError("Start the camera first")
            # Coalesce rapid button clicks; only the latest desired values
            # survive until the next SDK frame boundary.
            self._settings_request_id += 1
            self._pending_settings = (self._settings_request_id, gain, exposure_us)
            return self._settings_request_id

    def set_preview_mode(self, mode):
        if mode not in ("auto", "fixed"):
            raise ValueError("Preview mode must be auto or fixed")
        with self._lock:
            self._preview_mode = mode
        return mode

    def set_debayer(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Debayer must be on or off")
        with self._lock:
            self._debayer = enabled
        return enabled

    def _preview_loop(self):
        last_preview_complete = None
        try:
            while not self._stop.is_set():
                try:
                    raw = self._raw_mailbox.get(timeout=0.15)
                except Empty:
                    continue
                if self._stop.is_set():
                    break
                with self._lock:
                    mode, debayer = self._preview_mode, self._debayer
                t0 = time.monotonic()
                stats = raw16_statistics(raw)
                jpeg = raw16_to_jpeg(raw, stretch=mode, debayer=debayer)
                finished = time.monotonic()
                duration_ms = (finished - t0) * 1000.0
                interval = finished - last_preview_complete if last_preview_complete is not None else None
                last_preview_complete = finished
                with self._lock:
                    self._image = jpeg
                    self._sequence += 1
                    self._preview_ms = round(duration_ms, 1)
                    self._raw_mean_adu = stats["raw_mean_adu"]
                    self._raw_p99_adu = stats["raw_p99_adu"]
                    self._raw_saturated_percent = stats["raw_saturated_percent"]
                    if interval is not None and interval > 0:
                        rate = 1 / interval
                        prior = self._preview_fps
                        self._preview_fps = round(rate if prior == 0 else 0.25 * rate + 0.75 * prior, 2)
        except Exception as exc:
            with self._lock:
                self._preview_error = f"JPEG preview failed: {exc}"
            self._stop.set()

    def _run(self):
        driver = None
        error = None
        try:
            if self._stop.is_set():
                return
            driver = self._driver_factory()
            driver.open()
            with self._lock:
                gain, exposure_us = self._gain, self._exposure_us
            # Exposure-before-gain is needed by the tested SVBONY SDK.
            exposure_us = driver.set_control(EXPOSURE, exposure_us)
            gain = driver.set_control(GAIN, gain)
            with self._lock:
                self._gain, self._exposure_us = gain, exposure_us
            driver.start()  # only ONE stream start per camera open session
            raw = C.create_string_buffer(RAW_BYTES)
            last_capture = None
            timeouts = 0
            with self._lock:
                self._phase = "running"
                self._preview_thread = threading.Thread(
                    target=self._preview_loop, name="sv705c-preview", daemon=True
                )
                self._preview_thread.start()
            while not self._stop.is_set():
                with self._lock:
                    requested = self._pending_settings
                    self._pending_settings = None
                if requested is not None:
                    request_id, requested_gain, requested_exposure = requested
                    exposure_us = driver.set_control(EXPOSURE, requested_exposure)
                    gain = driver.set_control(GAIN, requested_gain)
                    with self._lock:
                        self._gain, self._exposure_us = gain, exposure_us
                        self._settings_applied_id = request_id

                try:
                    driver.get_frame(raw, frame_wait_ms(exposure_us))
                except SDKError as exc:
                    if exc.code == 11 and timeouts < 3 and not self._stop.is_set():
                        timeouts += 1
                        continue
                    raise
                timeouts = 0
                now = time.monotonic()
                if last_capture is not None and now > last_capture:
                    rate = 1.0 / (now - last_capture)
                    with self._lock:
                        prior = self._capture_fps
                        self._capture_fps = round(rate if prior == 0 else 0.25 * rate + 0.75 * prior, 2)
                last_capture = now
                # No artificial 250ms throttle, no full-frame backlog.
                # Copy raw bytes only when the JPEG thread is ready to accept.
                if not self._stop.is_set() and self._raw_mailbox.empty():
                    try:
                        self._raw_mailbox.put_nowait(raw.raw)
                    except Full:
                        pass
        except Exception as exc:
            error = str(exc)
        finally:
            self._stop.set()
            preview = self._preview_thread
            if preview is not None and preview.is_alive():
                preview.join(timeout=5)
            if driver is not None:
                try:
                    driver.close()
                except Exception as exc:
                    if error is None:
                        error = f"SDK cleanup failed: {exc}"
            with self._lock:
                self._phase = "error" if error or self._preview_error else "stopped"
                self._error = error or self._preview_error
                self._image = None
