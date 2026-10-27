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

    def status(self):
        with self._lock:
            return {
                "phase": self._phase, "last_error": self._error,
                "frame_number": self._sequence, "has_frame": self._image is not None,
                "gain": self._gain, "exposure_us": self._exposure_us,
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
            self._commands.put_nowait((gain, exposure_us))

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
            with self._lock:
                self._phase = "running"
            while not self._stop.is_set():
                try:
                    while True:
                        requested_gain, requested_exposure = self._commands.get_nowait()
                        exposure_us = driver.set_control(EXPOSURE, requested_exposure)
                        gain = driver.set_control(GAIN, requested_gain)
                        with self._lock:
                            self._gain, self._exposure_us = gain, exposure_us
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
                if now - last_preview < 0.75:
                    continue
                jpeg = raw16_to_jpeg(raw)
                last_preview = now
                with self._lock:
                    self._image = jpeg
                    self._sequence += 1
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
