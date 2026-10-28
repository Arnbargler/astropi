"""Lossless science output and optional colour/mono quicklooks from SV705C RAW16.

RAW16 preserves SDK bytes; FITS preserves all original 12-bit numeric samples.
JPEG/PNG display colour is a GRBG 2x2 superpixel at half output resolution.
For 2x2 binning, the sensor supports Bayer-preserving binning but the SDK's
Bayer phase is provisionally assumed GRBG pending real colour-target verification.
"""
from datetime import timedelta
from io import BytesIO

import numpy as np
from PIL import Image

from astropi.camera.preview import _stretch_lut
from astropi.camera.sdk import WIDTH, HEIGHT, frame_bytes, frame_dimensions

FORMATS = ("raw", "fits", "jpg", "png")
EXTENSIONS = {"raw": "raw16", "fits": "fits", "jpg": "jpg", "png": "png"}


def validate_formats(formats):
    if not isinstance(formats, list) or not formats or any(
        type(fmt) is not str or fmt not in FORMATS for fmt in formats
    ) or len(set(formats)) != len(formats):
        raise ValueError("Select one or more unique formats: RAW, FITS, JPG, PNG")
    return tuple(fmt for fmt in FORMATS if fmt in formats)


def raw_pixels(raw, *, binning=1):
    width, height = frame_dimensions(binning)
    if memoryview(raw).nbytes != frame_bytes(binning):
        raise ValueError("Unexpected SV705C RAW16 buffer length")
    return np.frombuffer(raw, dtype="<u2", count=width * height).reshape(height, width)


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


def fits_bytes(raw, *, exposure_us, gain, received_at, binning=1):
    """Return a valid 2D primary FITS HDU with unsigned 12-bit CFA pixel values.

    DATE-OBS is an estimated exposure START (receipt - requested duration).
    The SVBONY SDK supplies no hardware exposure timestamps here.
    """
    pixels = raw_pixels(raw, binning=binning)
    width, height = frame_dimensions(binning)
    # FITS BITPIX=16 encodes signed int16 big-endian. Subtract BZERO so FITS
    # readers reconstruct physical unsigned 0..4095 sensor digital numbers.
    image = ((pixels >> 4).astype(np.int32) - 32768).astype(">i2").tobytes()
    start = received_at - timedelta(microseconds=exposure_us)
    cards = [
        _card("SIMPLE", True), _card("BITPIX", 16), _card("NAXIS", 2),
        _card("NAXIS1", width), _card("NAXIS2", height),
        _card("BSCALE", 1), _card("BZERO", 32768),
        _card("INSTRUME", "SVBONY SV705C"),
        _card("EXPTIME", exposure_us / 1_000_000),
        _card("GAIN", gain),
        _card("DATE-OBS", start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:26]),
        _card("DATE-END", received_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:26]),
        _card("TIMESYS", "UTC"),
        _card("TIMEQUAL", "ESTIMATED"),
        _card("XBINNING", binning), _card("YBINNING", binning),
        b"END".ljust(80),
    ]
    # Do not claim a known Bayer pattern for 2x2 until its SDK output has
    # been inspected on the actual camera. Preserve full binned RAW samples.
    if binning == 1:
        cards.insert(7, _card("BAYERPAT", "GRBG"))
    header = b"".join(cards)
    header += b" " * (-len(header) % 2880)
    return header + image + (b"\0" * (-len(image) % 2880))


def quicklook_image(raw, stretch="auto", *, binning=1, debayer=True):
    """Half-output-size GRBG colour quicklook or un-demosaiced green-site mono.

    Binned GRBG phase is provisional; never changes the underlying RAW/FITS.
    """
    if type(debayer) is not bool:
        raise ValueError("Debayer must be on or off")
    pixels = raw_pixels(raw, binning=binning)
    width, height = frame_dimensions(binning)
    if not debayer:
        plane = pixels[0::2, 0::2] >> 4
        return Image.fromarray(_stretch_lut(plane, stretch)[plane], "L")
    red = pixels[0::2, 1::2] >> 4
    blue = pixels[1::2, 0::2] >> 4
    green = ((pixels[0::2, 0::2] >> 4) + (pixels[1::2, 1::2] >> 4)) // 2
    rgb = np.empty((height // 2, width // 2, 3), dtype=np.uint8)
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
