"""Single SDK-owning thread, command queue and shared read-only JPEG frame."""
import ctypes as C
from queue import Empty, Full, Queue
import threading
import time

from .sdk import SVBDriver, SDKError, RAW_BYTES, GAIN, EXPOSURE
from .preview import raw16_to_jpeg


class CameraWorker:
    def __init__(self, driver_factory=SVBDriver):
        self._driver_factory = driver_factory
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._commands = Queue(maxsize=8)
        self._phase = "stopped"
        self._error = None
        self._image = None
        self._sequence = 0
        self._gain = 0
        self._exposure_us = 100_000
        self._settings_request_id = 0
        self._settings_applied_id = 0
        self._capture_fps = 0.0
        self._preview_fps = 0.0
        self._preview_ms = 0.0

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
            }

    def frame(self):
        with self._lock:
            return self._image, self._sequence

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._commands = Queue(maxsize=8)
            self._stop = threading.Event()
            self._phase = "connecting"
            self._error = None
            self._image = None
            self._sequence = 0
            self._settings_request_id = 0
            self._settings_applied_id = 0
            self._capture_fps = self._preview_fps = self._preview_ms = 0.0
            self._thread = threading.Thread(target=self._run, name="sv705c-sdk", daemon=True)
            self._thread.start()
            return True

    def stop(self):
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                return False
            self._phase = "stopping"
            self._stop.set()
            return True

    def configure(self, gain, exposure_us):
        if type(gain) is not int or not 0 <= gain <= 100:
            raise ValueError("Gain must be an integer from 0 to 100")
        if type(exposure_us) is not int or not 10_000 <= exposure_us <= 5_000_000:
            raise ValueError("Exposure must be between 10 and 5000 ms")
        with self._lock:
            if self._phase not in ("connecting", "running"):
                raise RuntimeError("Start the camera first")
            request_id = self._settings_request_id + 1
            self._commands.put_nowait((request_id, gain, exposure_us))
            self._settings_request_id = request_id
            return request_id

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
            # Initialize exposure first; some SVBONY SDK versions reject gain otherwise.
            exposure_us = driver.set_control(EXPOSURE, exposure_us)
            gain = driver.set_control(GAIN, gain)
            with self._lock:
                self._gain, self._exposure_us = gain, exposure_us
            driver.start()  # only ONE stream start per camera open session
            raw = C.create_string_buffer(RAW_BYTES)
            timeouts = 0
            last_preview = 0.0
            last_capture = None
            last_preview_complete = None
            with self._lock:
                self._phase = "running"
            while not self._stop.is_set():
                try:
                    while True:
                        request_id, requested_gain, requested_exposure = self._commands.get_nowait()
                        exposure_us = driver.set_control(EXPOSURE, requested_exposure)
                        gain = driver.set_control(GAIN, requested_gain)
                        with self._lock:
                            self._gain, self._exposure_us = gain, exposure_us
                            self._settings_applied_id = request_id
                except Empty:
                    pass
                wait_ms = min(8_000, max(2_500, int(exposure_us / 1000) + 1_500))
                try:
                    driver.get_frame(raw, wait_ms)
                except SDKError as exc:
                    if exc.code == 11 and timeouts < 3 and not self._stop.is_set():
                        timeouts += 1
                        continue
                    raise
                timeouts = 0
                now = time.monotonic()
                if last_capture is not None and now > last_capture:
                    measured = 1.0 / (now - last_capture)
                    with self._lock:
                        previous = self._capture_fps
                        self._capture_fps = round(measured if previous == 0 else 0.25 * measured + 0.75 * previous, 2)
                last_capture = now
                # Four previews/second maximum, not the old 750ms artificial cap.
                # Acquisition continues between previews; source RAW is never altered.
                if now - last_preview < 0.25:
                    continue
                jpeg = raw16_to_jpeg(raw)
                finished = time.monotonic()
                processing_ms = 1000.0 * (finished - now)
                if last_preview_complete is not None and finished > last_preview_complete:
                    measured = 1.0 / (finished - last_preview_complete)
                else:
                    measured = 0.0
                last_preview = finished
                last_preview_complete = finished
                with self._lock:
                    self._image = jpeg
                    self._sequence += 1
                    self._preview_ms = round(processing_ms, 1)
                    if measured:
                        previous = self._preview_fps
                        self._preview_fps = round(measured if previous == 0 else 0.25 * measured + 0.75 * previous, 2)
        except Exception as exc:
            error = str(exc)
        finally:
            if driver is not None:
                try:
                    driver.close()
                except Exception as exc:
                    if error is None:
                        error = f"SDK cleanup failed: {exc}"
            with self._lock:
                self._phase = "error" if error else "stopped"
                self._error = error
                self._image = None
