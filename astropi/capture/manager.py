"""Single-camera capture jobs: one shot or a bounded consecutive frame sequence.

A sequence consumes the NEXT full RAW16 frame only after the preceding frame
has been safely written. The SDK thread never waits for disk writes and no
unbounded RAW queue exists. Jobs live on the Pi, independent of browser tabs.
"""
from datetime import datetime, timezone
import threading
import uuid

from .formats import validate_formats


class CaptureBusy(RuntimeError):
    pass


class CaptureManager:
    MAX_FRAMES = 100

    def __init__(self, storage):
        self.storage = storage
        self._lock = threading.Lock()
        self._pending = False
        self._stop_after_write = False
        self._sequence_stretch = None
        self._state = self._initial()
        self._writer_thread = None

    @staticmethod
    def _initial():
        return dict(
            id=None, phase="idle", formats=[], files=[],
            directory=None, directories=[], total_bytes=0,
            error=None, time_received_utc=None,
            total_frames=0, completed_frames=0, current_frame=0,
            cancel_requested=False,
        )

    def status(self):
        with self._lock:
            return {
                **self._state,
                "files": [dict(x) for x in self._state["files"]],
                "formats": list(self._state["formats"]),
                "directories": list(self._state["directories"]),
            }

    def active_sequence(self):
        with self._lock:
            return self._state["total_frames"] > 1 and self._state["phase"] in (
                "waiting", "saving",
            )

    def request(self, selected, count=1, stretch=None):
        """Start capture. One-shot remains the default for existing API."""
        formats = validate_formats(selected)
        if stretch is not None and stretch not in ("auto", "fixed"):
            raise ValueError("Quicklook stretch must be auto or fixed")
        if type(count) is not int or not 1 <= count <= self.MAX_FRAMES:
            raise ValueError(f"Frame count must be an integer from 1 to {self.MAX_FRAMES}")
        with self._lock:
            if self._state["phase"] in ("waiting", "saving"):
                raise CaptureBusy("Another capture or sequence is still active")
            # The whole session must have sufficient headroom before it starts.
            # Every actual frame will also be checked immediately before writing.
            self.storage.preflight(formats, count=count)
            identifier = uuid.uuid4().hex[:12]
            self._state = self._initial()
            self._state.update(
                id=identifier, phase="waiting", formats=list(formats),
                total_frames=count,
            )
            self._pending = True
            self._stop_after_write = False
            self._sequence_stretch = stretch if count > 1 else None
            return identifier

    def cancel(self):
        """Stop at a frame boundary, never halfway through a file write."""
        with self._lock:
            phase = self._state["phase"]
            if phase not in ("waiting", "saving"):
                raise RuntimeError("No active capture or sequence to cancel")
            self._state["cancel_requested"] = True
            self._pending = False
            if phase == "waiting":
                self._state["phase"] = "cancelled"
            # If saving, the writer finishes the current full frame first.
            return self._state["id"]

    def accept_frame(self, raw, *, gain, exposure_us, stretch, binning=1):
        """SDK thread submits only one immutable raw frame per completed write."""
        with self._lock:
            if not self._pending or self._state["phase"] != "waiting":
                return False
            self._pending = False
            identifier = self._state["id"]
            formats = tuple(self._state["formats"])
            index = self._state["completed_frames"] + 1
            count = self._state["total_frames"]
            if self._sequence_stretch is not None:
                stretch = self._sequence_stretch
            self._state["current_frame"] = index
            self._state["phase"] = "saving"
            received_at = datetime.now(timezone.utc)
            self._state["time_received_utc"] = received_at.isoformat()
            # The ctypes SDK buffer is overwritten on the next get_frame().
            frame = bytes(raw)
            self._writer_thread = threading.Thread(
                target=self._save,
                args=(identifier, frame, formats, gain, exposure_us,
                      stretch, received_at, index, count, binning),
                name="sv705c-capture-save", daemon=False,
            )
            self._writer_thread.start()
            return True

    def _save(self, identifier, frame, formats, gain, exposure_us,
              stretch, received_at, index, count, binning):
        try:
            # Sequence details are included per-frame in metadata.json.
            params = dict(
                gain=gain, exposure_us=exposure_us,
                stretch=stretch, received_at=received_at,
                sequence=dict(id=identifier, index=index, count=count)
                         if count > 1 else None,
            )
            if binning != 1:
                params["binning"] = binning
            result = self.storage.save(frame, formats, **params)
        except Exception as exc:
            with self._lock:
                if self._state["id"] == identifier:
                    self._pending = False
                    self._state["phase"] = "error"
                    self._state["error"] = str(exc)
            return
        with self._lock:
            if self._state["id"] != identifier:
                return
            self._state["completed_frames"] += 1
            self._state["directory"] = result["directory"]
            self._state["directories"].append(result["directory"])
            self._state["files"] = list(result["files"])  # most recent frame
            self._state["total_bytes"] += result["total_bytes"]
            if self._state["cancel_requested"]:
                self._state["phase"] = "cancelled"
            elif self._stop_after_write:
                self._state["phase"] = "error"
                self._state["error"] = "Camera stopped during capture sequence"
            elif self._state["completed_frames"] == self._state["total_frames"]:
                self._state["phase"] = "done"
            else:
                self._pending = True
                self._state["phase"] = "waiting"

    def fail_waiting(self, reason):
        """Called by the SDK thread on stop/error, including mid-save shutdown."""
        with self._lock:
            if self._state["phase"] == "waiting":
                self._pending = False
                self._state["phase"] = "error"
                self._state["error"] = reason
            elif self._state["phase"] == "saving":
                self._stop_after_write = True
                self._pending = False
