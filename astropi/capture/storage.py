"""UUID-guarded USB recording with directory-fd-relative atomic file writes."""
import hashlib
import json
import os
import secrets
from datetime import timezone
from pathlib import Path

from astropi.camera.sdk import RAW_BYTES
from astropi.status import storage_status
from .formats import EXTENSIONS, fits_bytes, quicklook_image, quicklook_bytes

# Conservative estimates for one exposure. Refuse capture if drive is low.
_RESERVE_BYTES = 64 * 1024 * 1024
_ESTIMATED = {
    "raw": RAW_BYTES,
    "fits": RAW_BYTES + 2880 * 2,
    "jpg": 12 * 1024 * 1024,
    "png": 24 * 1024 * 1024,
}


class StorageError(RuntimeError):
    pass


class CaptureStorage:
    def __init__(self, settings, verifier=storage_status):
        self.mount = Path(settings.storage_mount)
        self.uuid = settings.storage_uuid
        self._verify = verifier

    def preflight(self, formats, *, count=1):
        status = self._verify(self.mount, self.uuid)
        needed = _RESERVE_BYTES + count * sum(_ESTIMATED[k] for k in formats)
        if not status.get("ready"):
            raise StorageError("Recording refused: USB drive " + status.get("state", "unavailable"))
        if status.get("free_bytes") is None or status["free_bytes"] < needed:
            raise StorageError(
                f"Recording refused: insufficient USB space (need ~{needed // 1048576} MiB free)"
            )
        return status

    @staticmethod
    def _create_dir(parent_fd, name):
        try:
            os.mkdir(name, mode=0o750, dir_fd=parent_fd)
        except FileExistsError:
            pass
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        return os.open(name, flags, dir_fd=parent_fd)

    @staticmethod
    def _atomic_write(dir_fd, name, payload):
        """Never open a file by the original mount pathname after validation."""
        partial = name + ".partial"
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o640, dir_fd=dir_fd)
        try:
            view = memoryview(payload)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise OSError("short filesystem write")
                view = view[count:]
            os.fsync(fd)
        except BaseException:
            try:
                os.unlink(partial, dir_fd=dir_fd)
            except OSError:
                pass
            raise
        finally:
            os.close(fd)
        os.rename(partial, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
        return len(payload), hashlib.sha256(payload).hexdigest()

    def save(self, raw, formats, *, gain, exposure_us, received_at, stretch,
             sequence=None, binning=1):
        from astropi.camera.sdk import frame_dimensions, frame_bytes
        width, height = frame_dimensions(binning)
        if memoryview(raw).nbytes != frame_bytes(binning):
            raise StorageError("Wrong RAW16 size for configured binning")
        self.preflight(formats)  # Repeat check after capture and before writes.
        # Pin the verified mounted filesystem by opening its root; no fallback
        # to the same pathname on microSD if the USB device disappears.
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        root_fd = os.open(self.mount, flags)
        try:
            root_stat = os.fstat(root_fd)
            path_stat = os.stat(self.mount, follow_symlinks=False)
            if root_stat.st_dev != path_stat.st_dev or root_stat.st_ino != path_stat.st_ino:
                raise StorageError("USB mount changed while opening recording directory")
            self.preflight(formats)
            capture_fd = self._create_dir(root_fd, "captures")
            try:
                if os.fstat(capture_fd).st_dev != root_stat.st_dev:
                    raise StorageError("Capture directory is not on USB filesystem")
                folder = received_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S_%f") + "_" + secrets.token_hex(3)
                # Publish a complete capture set atomically. Any interrupted
                # save stays explicitly marked '.partial' and is never shown
                # as a complete capture.
                working = folder + ".partial"
                os.mkdir(working, mode=0o750, dir_fd=capture_fd)
                shot_fd = os.open(working, flags, dir_fd=capture_fd)
                try:
                    if os.fstat(shot_fd).st_dev != root_stat.st_dev:
                        raise StorageError("Capture shot directory left verified USB filesystem")
                    relative = "captures/" + folder
                    files = []
                    quicklook = None
                    for fmt in formats:
                        self.preflight((fmt,))  # UUID, mount, writeability, headroom again.
                        if fmt == "raw":
                            payload = raw
                        elif fmt == "fits":
                            payload = fits_bytes(
                                raw, gain=gain, exposure_us=exposure_us,
                                received_at=received_at, binning=binning
                            )
                        else:
                            if quicklook is None:
                                quicklook = quicklook_image(raw, stretch=stretch,
                                                            binning=binning)
                            payload = quicklook_bytes(quicklook, fmt)
                        name = f"sv705c.{EXTENSIONS[fmt]}"
                        count, digest = self._atomic_write(shot_fd, name, payload)
                        files.append(dict(format=fmt.upper(), path=relative + "/" + name,
                                          bytes=count, sha256=digest))
                    metadata = dict(
                        camera="SVBONY SV705C", width=width, height=height,
                        binning=binning, pixel_format="RAW16_LE",
                        bayer="GRBG" if binning == 1 else "unverified at 2x2",
                        bits_valid=12,
                        native_left_shift=4, gain=gain,
                        exposure_us=exposure_us,
                        time_received_utc=received_at.isoformat(),
                        time_source="Pi host UTC, SDK hardware timestamp unavailable",
                        quicklook_stretch=stretch,
                        quicklook_dimensions=list(quicklook.size) if quicklook else
                            [width // 2, height // 2],
                        fits_data="unsigned 12-bit ADU with FITS BZERO=32768",
                        files=files,
                    )
                    if sequence is not None:
                        metadata["sequence"] = dict(sequence)
                    manifest = json.dumps(metadata, indent=2, ensure_ascii=True).encode() + b"\n"
                    self._atomic_write(shot_fd, "metadata.json", manifest)
                    os.fsync(shot_fd)
                    # Before publishing, verify that the root pathname still
                    # identifies the same pinned USB filesystem.
                    if not self._verify(self.mount, self.uuid).get("ready"):
                        raise StorageError("USB mount no longer verified at capture commit")
                    active_stat = os.stat(self.mount, follow_symlinks=False)
                    if (active_stat.st_dev, active_stat.st_ino) != (
                        root_stat.st_dev, root_stat.st_ino
                    ):
                        raise StorageError("USB mount changed during capture save")
                    os.rename(working, folder, src_dir_fd=capture_fd, dst_dir_fd=capture_fd)
                    os.fsync(capture_fd)
                    return dict(directory=relative, files=files,
                                total_bytes=sum(item["bytes"] for item in files))
                finally:
                    os.close(shot_fd)
            finally:
                os.close(capture_fd)
        finally:
            os.close(root_fd)
