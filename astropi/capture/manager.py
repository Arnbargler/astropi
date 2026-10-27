"""One-shot capture requests use the NEXT full RAW16 SDK frame, never JPEG.

Capture and recording jobs are independent of browser connection. Only one
active request is permitted. Saving runs in a distinct worker thread so the
camera can continue streaming. A new job can start after the previous finishes.
"""
from datetime import datetime, timezone
import threading
import uuid

from .formats import validate_formats


class CaptureBusy(RuntimeError):
    pass


class CaptureManager:
    def __init__(self, storage):
        self.storage = storage
        self._lock = threading.Lock()
        self._pending = None
        self._state = dict(id=None, phase="idle", formats=[], files=[],
                           directory=None, total_bytes=0, error=None,
                           time_received_utc=None)
        self._writer_thread = None

    def status(self):
        with self._lock:
            return {
                **self._state,
                "files": [dict(x) for x in self._state["files"]],
                "formats": list(self._state["formats"]),
            }

    def request(self, selected):
        formats = validate_formats(selected)
        with self._lock:
            if self._state["phase"] in ("waiting", "saving"):
                raise CaptureBusy("A frame capture is already in progress")
            # Verify the UUID and available capacity BEFORE accepting a job.
            # This also rejects the empty microSD mountpoint when USB is missing.
            self.storage.preflight(formats)
            identifier = uuid.uuid4().hex[:12]
            self._state = dict(id=identifier, phase="waiting", formats=list(formats),
                               files=[], directory=None, total_bytes=0, error=None,
                               time_received_utc=None)
            self._pending = (identifier, formats)
            return identifier

    def accept_frame(self, raw, *, gain, exposure_us, stretch):
        """Called once per SDK frame; copies data ONLY when a job is pending."""
        with self._lock:
            pending = self._pending
            if pending is None or self._state["phase"] != "waiting":
                return False
            self._pending = None
            identifier, formats = pending
            self._state["phase"] = "saving"
            received_at = datetime.now(timezone.utc)
            self._state["time_received_utc"] = received_at.isoformat()
            # Copy before the acquisition loop reuses its ctypes buffer.
            frame = bytes(raw)
            self._writer_thread = threading.Thread(
                target=self._save, args=(identifier, frame, formats, gain,
                                         exposure_us, stretch, received_at),
                name="sv705c-capture-save", daemon=False,
            )
            self._writer_thread.start()
            return True

    def _save(self, identifier, frame, formats, gain, exposure_us, stretch, received_at):
        try:
            result = self.storage.save(
                frame, formats, gain=gain, exposure_us=exposure_us,
                stretch=stretch, received_at=received_at,
            )
        except Exception as exc:
            with self._lock:
                if self._state["id"] == identifier:
                    self._state["phase"] = "error"
                    self._state["error"] = str(exc)
            return
        with self._lock:
            if self._state["id"] == identifier:
                self._state["phase"] = "done"
                self._state.update(result)

    def fail_waiting(self, reason):
        with self._lock:
            if self._state["phase"] == "waiting":
                self._pending = None
                self._state["phase"] = "error"
                self._state["error"] = reason
