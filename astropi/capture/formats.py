"""Conservative scientific formats and colour quicklooks for SV705C RAW16.

RAW preserves byte-for-byte original SDK data (little endian, 12 bit << 4).
FITS is unsigned 12-bit Bayer samples, full sensor resolution, standards-safe
signed BIG-endian BITPIX=16 storage with BZERO=32768 / BSCALE=1. The resulting
physical values are 0..4095. No interpolation, stretch or data loss in FITS.
JPEG/PNG are colour 2x2 Bayer superpixel quicklooks at half linear resolution.
"""
from datetime import timedelta
from io import BytesIO

import numpy as np
from PIL import Image

from astropi.camera.preview import _stretch_lut
from astropi.camera.sdk import WIDTH, HEIGHT, RAW_BYTES

FORMATS = ("raw", "fits", "jpg", "png")
EXTENSIONS = {"raw": "raw16", "fits": "fits", "jpg": "jpg", "png": "png"}


def validate_formats(formats):
    if not isinstance(formats, list) or not formats or any(
        type(fmt) is not str or fmt not in FORMATS for fmt in formats
    ) or len(set(formats)) != len(formats):
        raise ValueError("Select one or more unique formats: RAW, FITS, JPG, PNG")
    return tuple(fmt for fmt in FORMATS if fmt in formats)


def raw_pixels(raw):
    if memoryview(raw).nbytes != RAW_BYTES:
        raise ValueError("Unexpected full-frame RAW16 buffer length")
    return np.frombuffer(raw, dtype="<u2", count=WIDTH * HEIGHT).reshape(HEIGHT, WIDTH)


def _card(key, value):
    if len(key) > 8:
        raise ValueError("FITS keyword too long")
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        field = "'{}'".format(escaped)
        if len(field) > 70:
            raise ValueError("FITS string field too long")
        return f"{key:<8}= {field:<20}".ljust(80).encode("ascii")
    if isinstance(value, bool):
        field = "T" if value else "F"
    elif isinstance(value, float):
        field = f"{value:.6f}"
    else:
        field = str(int(value))
    return f"{key:<8}= {field:>20}".ljust(80).encode("ascii")


def fits_bytes(raw, *, exposure_us, gain, received_at):
    """Return a valid 2D primary FITS HDU with unsigned 12-bit CFA pixel values.

    DATE-OBS is an estimated exposure START (receipt - requested duration).
    The SVBONY SDK supplies no hardware exposure timestamps here.
    """
    pixels = raw_pixels(raw)
    # FITS BITPIX=16 encodes signed int16 big-endian. Subtract BZERO so FITS
    # readers reconstruct physical unsigned 0..4095 sensor digital numbers.
    image = ((pixels >> 4).astype(np.int32) - 32768).astype(">i2").tobytes()
    start = received_at - timedelta(microseconds=exposure_us)
    cards = [
        _card("SIMPLE", True), _card("BITPIX", 16), _card("NAXIS", 2),
        _card("NAXIS1", WIDTH), _card("NAXIS2", HEIGHT),
        _card("BSCALE", 1), _card("BZERO", 32768),
        _card("BAYERPAT", "GRBG"),
        _card("INSTRUME", "SVBONY SV705C"),
        _card("EXPTIME", exposure_us / 1_000_000),
        _card("GAIN", gain),
        _card("DATE-OBS", start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:26]),
        _card("DATE-END", received_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:26]),
        _card("TIMESYS", "UTC"),
        _card("TIMEQUAL", "ESTIMATED"),
        _card("XBINNING", 1), _card("YBINNING", 1),
        b"END".ljust(80),
    ]
    header = b"".join(cards)
    header += b" " * (-len(header) % 2880)
    return header + image + (b"\0" * (-len(image) % 2880))


def quicklook_image(raw, stretch="auto"):
    """Half-resolution GRBG superpixel colour; NOT calibrated/demosaiced science."""
    pixels = raw_pixels(raw)
    red = pixels[0::2, 1::2] >> 4
    blue = pixels[1::2, 0::2] >> 4
    green = ((pixels[0::2, 0::2] >> 4) + (pixels[1::2, 1::2] >> 4)) // 2
    rgb = np.empty((HEIGHT // 2, WIDTH // 2, 3), dtype=np.uint8)
    for channel, plane in enumerate((red, green, blue)):
        rgb[:, :, channel] = _stretch_lut(plane, stretch)[plane]
    return Image.fromarray(rgb, "RGB")


def quicklook_bytes(image, fmt):
    stream = BytesIO()
    if fmt == "jpg":
        image.save(stream, format="JPEG", quality=90, optimize=False)
    elif fmt == "png":
        image.save(stream, format="PNG", compress_level=3)
    else:
        raise ValueError("Unsupported quicklook format")
    return stream.getvalue()
