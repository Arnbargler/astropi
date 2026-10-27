"""Fast display-only SV705C previews; RAW16 source buffers are never mutated.

Both paths generate ~964x545 display JPEGs from the 3856x2180 GRBG mosaic.
Debayer ON: inexpensive colour sampling of 4x4 Bayer blocks.
Debayer OFF: monochrome sampling of green photosites (no colour interpolation).
"""
from io import BytesIO

import numpy as np
from PIL import Image

from .sdk import WIDTH, HEIGHT, RAW_BYTES

_LEVELS = np.arange(4096, dtype=np.float32)
# Precompute fixed gamma so preview processing requires no per-pixel power().
_FIXED_LUT = (np.power(_LEVELS / 4095.0, 0.55) * 255).astype(np.uint8)


def _stretch_lut(plane, stretch):
    if stretch == "fixed":
        return _FIXED_LUT

    # Sample a small fraction of the preview image for per-frame auto stretch.
    sample = plane[::3, ::3]
    low, high = np.percentile(sample, (1, 99.5))
    scaled = np.clip((_LEVELS - low) / max(high - low, 32), 0, 1)
    return (np.power(scaled, 0.8) * 255).astype(np.uint8)


def raw16_to_jpeg(raw, stretch="auto", debayer=True) -> bytes:
    """Render a colour or fast greyscale JPEG without modifying RAW16 pixels."""
    if stretch not in ("auto", "fixed"):
        raise ValueError("Unsupported preview stretch mode")
    if type(debayer) is not bool:
        raise ValueError("debayer must be a boolean")
    if memoryview(raw).nbytes != RAW_BYTES:
        raise ValueError("Unexpected SV705C RAW16 buffer length")

    pixels = np.frombuffer(raw, dtype="<u2", count=WIDTH * HEIGHT).reshape(HEIGHT, WIDTH)
    if not debayer:
        # Bayer GRBG begins with green. One green pixel per 4x4 mosaic block.
        # This is sensor-sampled monochrome, not a separate greyscale exposure.
        mono = pixels[0::4, 0::4] >> 4
        out = BytesIO()
        Image.fromarray(_stretch_lut(mono, stretch)[mono], "L").save(
            out, format="JPEG", quality=80
        )
        return out.getvalue()

    # GRBG = G R / B G. Sample two red, two blue and four green photosites
    # per 4x4 block. Summing 12-bit values stays safely within uint16.
    red = ((pixels[0::4, 1::4] >> 4) + (pixels[2::4, 3::4] >> 4)) // 2
    blue = ((pixels[1::4, 0::4] >> 4) + (pixels[3::4, 2::4] >> 4)) // 2
    green = (
        (pixels[0::4, 0::4] >> 4) + (pixels[1::4, 1::4] >> 4) +
        (pixels[2::4, 2::4] >> 4) + (pixels[3::4, 3::4] >> 4)
    ) // 4

    # LUTs avoid a full float32 RGB tensor and per-pixel nonlinear transforms.
    rgb = np.empty((*red.shape, 3), dtype=np.uint8)
    for channel, plane in enumerate((red, green, blue)):
        rgb[:, :, channel] = _stretch_lut(plane, stretch)[plane]
    out = BytesIO()
    Image.fromarray(rgb, "RGB").save(out, format="JPEG", quality=80)
    return out.getvalue()


def raw16_statistics(raw) -> dict:
    """Sparse, un-stretched 12-bit sensor statistics for gain/exposure diagnosis."""
    if memoryview(raw).nbytes != RAW_BYTES:
        raise ValueError("Unexpected SV705C RAW16 buffer length")
    pixels = np.frombuffer(raw, dtype="<u2", count=WIDTH * HEIGHT).reshape(HEIGHT, WIDTH)
    sample = pixels[::16, ::16] >> 4
    return {
        "raw_mean_adu": round(float(sample.mean()), 1),
        "raw_p99_adu": int(np.percentile(sample, 99)),
        "raw_saturated_percent": round(float(np.mean(sample >= 4095) * 100), 2),
    }
