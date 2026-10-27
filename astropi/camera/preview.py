"""Display-only colour preview from verified GRBG RAW16 sensor bytes."""
from io import BytesIO
import numpy as np
from PIL import Image
from .sdk import WIDTH, HEIGHT, RAW_BYTES


def raw16_to_jpeg(raw, stretch="auto") -> bytes:
    """Make a display JPEG. Auto rescales each frame; fixed preserves brightness changes."""
    if stretch not in ("auto", "fixed"):
        raise ValueError("Unsupported preview stretch mode")
    if memoryview(raw).nbytes != RAW_BYTES:
        raise ValueError("Unexpected SV705C RAW16 buffer length")
    # SV705C hardware probe observed 12-bit values left-shifted four bits.
    p = np.frombuffer(raw, dtype="<u2", count=WIDTH * HEIGHT).reshape(HEIGHT, WIDTH) >> 4

    def mean(*tiles):
        total = np.zeros_like(tiles[0], dtype=np.float32)
        for tile in tiles:
            total += tile
        return total / len(tiles)

    # One 4x4 Bayer block -> one RGB pixel (964x545). GRBG = G R / B G.
    red = mean(p[0::4, 1::4], p[0::4, 3::4],
               p[2::4, 1::4], p[2::4, 3::4])
    blue = mean(p[1::4, 0::4], p[1::4, 2::4],
                p[3::4, 0::4], p[3::4, 2::4])
    green = mean(p[0::4, 0::4], p[0::4, 2::4], p[1::4, 1::4], p[1::4, 3::4],
                 p[2::4, 0::4], p[2::4, 2::4], p[3::4, 1::4], p[3::4, 3::4])
    rgb = np.stack((red, green, blue), axis=-1)
    if stretch == "auto":
        # Per-frame, per-channel stretch intentionally conceals brightness changes.
        # Excellent for faint-object visibility, misleading when evaluating gain.
        sample = rgb[::4, ::4, :]
        low = np.percentile(sample, 1, axis=(0, 1))
        high = np.percentile(sample, 99.5, axis=(0, 1))
        scaled = np.clip((rgb - low) / np.maximum(high - low, 32), 0, 1)
        gamma = 0.8
    else:
        # Identical sensor-to-screen transfer function across all frames and
        # channels: changing gain/exposure WILL affect displayed brightness.
        # Fixed gamma brightens shadows but has no frame-dependent normalizer.
        scaled = np.clip(rgb / 4095.0, 0, 1)
        gamma = 0.55
    result = (np.power(scaled, gamma) * 255).astype(np.uint8)
    out = BytesIO()
    Image.fromarray(result, "RGB").save(out, format="JPEG", quality=80)
    return out.getvalue()



def raw16_statistics(raw) -> dict:
    """Quick un-stretched 12-bit raw diagnostics; sampled sensor pixels, not JPEG."""
    if memoryview(raw).nbytes != RAW_BYTES:
        raise ValueError("Unexpected SV705C RAW16 buffer length")
    pixels = np.frombuffer(raw, dtype="<u2", count=WIDTH * HEIGHT).reshape(HEIGHT, WIDTH)
    sample = pixels[::16, ::16] >> 4
    return {
        "raw_mean_adu": round(float(sample.mean()), 1),
        "raw_p99_adu": int(np.percentile(sample, 99)),
        "raw_saturated_percent": round(float(np.mean(sample >= 4095) * 100), 2),
    }
