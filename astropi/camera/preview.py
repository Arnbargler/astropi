"""Fast display-only SV705C previews; RAW16 source buffers are never mutated.

Display-only JPEGs at ~964x545 for either 1x1 or 2x2 SV705C RAW16.
Debayer ON: inexpensive GRBG colour sampling; binned 2x2 keeps its own
Bayer mosaic on the Sony IMX585. The operator visually confirmed correct
2x2 colour preview on the actual SV705C (2026-10-28) with GRBG decoding.
Debayer OFF: fast monochrome sampling of green photosites.
"""
from io import BytesIO

import numpy as np
from PIL import Image

from .sdk import frame_dimensions, frame_bytes

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


def raw16_to_jpeg(raw, stretch="auto", debayer=True, *, binning=1) -> bytes:
    """Render a colour or fast greyscale JPEG without modifying RAW16 pixels."""
    if stretch not in ("auto", "fixed"):
        raise ValueError("Unsupported preview stretch mode")
    if type(debayer) is not bool:
        raise ValueError("debayer must be a boolean")
    width, height = frame_dimensions(binning)
    if memoryview(raw).nbytes != frame_bytes(binning):
        raise ValueError("Unexpected SV705C RAW16 buffer length")

    pixels = np.frombuffer(raw, dtype="<u2", count=width * height).reshape(height, width)
    if binning == 2:
        # IMX585 supports Bayer-preserving 2x2 binning. Decode the SDK's
        # provisional GRBG phase until a red/blue scene verifies it.
        # A 2x2 colour superpixel keeps preview size ~964x545.
        if not debayer:
            mono = pixels[0::2, 0::2] >> 4
            out = BytesIO()
            Image.fromarray(_stretch_lut(mono, stretch)[mono], "L").save(
                out, format="JPEG", quality=80
            )
            return out.getvalue()
        red = pixels[0::2, 1::2] >> 4
        blue = pixels[1::2, 0::2] >> 4
        green = ((pixels[0::2, 0::2] >> 4) +
                 (pixels[1::2, 1::2] >> 4)) // 2
        rgb = np.empty((*red.shape, 3), dtype=np.uint8)
        for channel, plane in enumerate((red, green, blue)):
            rgb[:, :, channel] = _stretch_lut(plane, stretch)[plane]
        out = BytesIO()
        Image.fromarray(rgb, "RGB").save(out, format="JPEG", quality=80)
        return out.getvalue()
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


def raw16_statistics(raw, *, binning=1) -> dict:
    """Sparse, un-stretched 12-bit signal readouts for gain/exposure feedback."""
    width, height = frame_dimensions(binning)
    if memoryview(raw).nbytes != frame_bytes(binning):
        raise ValueError("Unexpected SV705C RAW16 buffer length")
    pixels = np.frombuffer(raw, dtype="<u2", count=width * height).reshape(height, width)
    sample = pixels[::16, ::16] >> 4
    return {
        "raw_mean_adu": round(float(sample.mean()), 1),
        "raw_p99_adu": int(np.percentile(sample, 99)),
        "raw_saturated_percent": round(float(np.mean(sample >= 4095) * 100), 2),
    }
