"""Read-only integrity and FITS Bayer validation for saved AstroPi captures.

Usage:
    python -m astropi.capture.verify /media/astropi-data/captures/<shot-folder>

Checks SHA256, manifest sizes, FITS structural cards, 12-bit range, and when
RAW16 was also selected, EVERY sensor sample against the corresponding FITS
pixel. No disk writes and no dependency on optional astropy.
"""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def _fits_header(file):
    cards = {}
    header_len = 0
    with file.open("rb") as handle:
        while True:
            block = handle.read(2880)
            if len(block) != 2880:
                raise ValueError("Truncated FITS header")
            header_len += 2880
            for pos in range(0, len(block), 80):
                text = block[pos:pos + 80].decode("ascii")
                key = text[:8].strip()
                if key == "END":
                    return cards, header_len
                if text[8:10] != "= " or not key:
                    continue
                value = text[10:80].split("/", 1)[0].strip()
                if value.startswith("'"):
                    cards[key] = value.strip().strip("'").replace("''", "'")
                elif value in ("T", "F"):
                    cards[key] = value == "T"
                elif any(ch in value for ch in (".", "E")):
                    cards[key] = float(value)
                else:
                    cards[key] = int(value)


def check_capture(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "metadata.json").read_text())
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("No image entries in metadata")
    for entry in files:
        # All metadata paths must refer to files inside this capture directory.
        path = folder / Path(entry["path"]).name
        if path.name != Path(entry["path"]).name or path.parent != folder:
            raise ValueError("Unexpected file path")
        if path.stat().st_size != entry["bytes"]:
            raise ValueError(f"File-size mismatch: {path.name}")
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for part in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(part)
        if hasher.hexdigest() != entry["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {path.name}")

    fits = folder / "sv705c.fits"
    if not fits.exists():
        return {"files": len(files), "fits_checked": False, "raw_pixels_equal": None}

    from astropi.camera.sdk import frame_dimensions
    binning = manifest.get("binning", 1)
    width, height = frame_dimensions(binning)
    if manifest.get("width", width) != width or manifest.get("height", height) != height:
        raise ValueError("Capture metadata dimensions do not match binning")
    header, offset = _fits_header(fits)
    expected = {"SIMPLE": True, "BITPIX": 16, "NAXIS": 2,
                "NAXIS1": width, "NAXIS2": height,
                "BZERO": 32768, "BSCALE": 1,
                "XBINNING": binning, "YBINNING": binning}
    if binning == 1:
        expected["BAYERPAT"] = "GRBG"
    elif "BAYERPAT" in header:
        raise ValueError("2x2 FITS Bayer pattern is unverified; omit BAYERPAT")
    for key, value in expected.items():
        if header.get(key) != value:
            raise ValueError(f"FITS header mismatch: {key}")
    if fits.stat().st_size % 2880:
        raise ValueError("FITS file length not 2880-byte aligned")
    rawpath = folder / "sv705c.raw16"
    raw = None
    if rawpath.exists():
        if rawpath.stat().st_size != width * height * 2:
            raise ValueError("RAW16 size incorrect")
        raw = np.memmap(rawpath, dtype="<u2", mode="r", shape=(height, width))
    science = np.memmap(fits, dtype=">i2", mode="r",
                        offset=offset, shape=(height, width))
    for row in range(0, height, 128):
        end = min(row + 128, height)
        values = science[row:end].astype(np.int32) + 32768
        if np.any(values > 4095) or np.any(values < 0):
            raise ValueError("FITS sensor values outside 12-bit range")
        if raw is not None and not np.array_equal(values, raw[row:end] >> 4):
            raise ValueError(f"FITS and RAW16 sensor pixels differ at row {row}")
    return {"files": len(files), "fits_checked": True,
            "raw_pixels_equal": True if raw is not None else None}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: python -m astropi.capture.verify /path/to/capture-folder")
        return 2
    try:
        outcome = check_capture(args[0])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("FAIL:", exc)
        return 1
    print(f"PASS: {outcome['files']} saved files match checksums and sizes.")
    if outcome["fits_checked"]:
        print("PASS: FITS structure and 12-bit Bayer sample range.")
        if outcome["raw_pixels_equal"] is True:
            print("PASS: All FITS pixels match the RAW16 sensor pixels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
