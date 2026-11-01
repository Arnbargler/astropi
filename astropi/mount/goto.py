"""Offline Messier target whitelist and J2000-to-date mean coordinates.

The AM3N accepts RA/Dec target setters in its date-based equatorial frame.
This approximate IAU-1976 precession matches Find's planning helper; actual
optical pointing still requires mount alignment and outdoor verification.
"""
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import json
import math
import re

_CATALOGUE = Path(__file__).resolve().parents[1] / "static/vendor/virtualsky/messier.json"
_TARGET = re.compile(r"M(?:[1-9]|[1-9][0-9]|10[0-9]|110)\Z")
_RAD = math.pi / 180


@lru_cache(maxsize=1)
def messier_catalogue():
    entries = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
    targets = {e["target"]["name"]: (float(e["ra"]["decimal"]),
                                      float(e["dec"]["decimal"])) for e in entries}
    if len(entries) != 110 or len(targets) != 110 or set(targets) != {
        f"M{n}" for n in range(1, 111)
    }:
        raise RuntimeError("Local Messier catalogue is invalid")
    return targets


def target_of_date(name, utc=None):
    """Return (RA degrees, Dec degrees) in mean equator/equinox of date."""
    if not isinstance(name, str) or not _TARGET.fullmatch(name):
        raise ValueError("GoTo requires a selected Messier target M1–M110")
    if utc is None:
        utc = datetime.now(timezone.utc)
    if not isinstance(utc, datetime) or utc.tzinfo is None:
        raise ValueError("UTC must be timezone-aware")
    ra, dec = messier_catalogue()[name]
    # Julian centuries since J2000.0 (JD 2451545.0).
    jd = utc.timestamp() / 86400 + 2440587.5
    t = (jd - 2451545.0) / 36525
    zeta = (2306.2181*t + 0.30188*t*t + 0.017998*t*t*t)/3600 * _RAD
    z = (2306.2181*t + 1.09468*t*t + 0.018203*t*t*t)/3600 * _RAD
    theta = (2004.3109*t - 0.42665*t*t - 0.041833*t*t*t)/3600 * _RAD
    a = math.cos(dec*_RAD)*math.sin(ra*_RAD+zeta)
    b = math.cos(theta)*math.cos(dec*_RAD)*math.cos(ra*_RAD+zeta) - math.sin(theta)*math.sin(dec*_RAD)
    c = math.sin(theta)*math.cos(dec*_RAD)*math.cos(ra*_RAD+zeta) + math.cos(theta)*math.sin(dec*_RAD)
    return ((math.degrees(math.atan2(a, b)+z)) % 360,
            math.degrees(math.asin(max(-1, min(1, c)))))


def goto_commands(ra_deg, dec_deg):
    """Explicit whitelisted LX200-like setter/GoTo sequence."""
    if not all(math.isfinite(x) for x in (ra_deg, dec_deg)) or not (
        0 <= ra_deg < 360 and -90 <= dec_deg <= 90
    ):
        raise ValueError("Out-of-range GoTo coordinates")
    ra_seconds = round(ra_deg * 240) % 86400
    h, rem = divmod(ra_seconds, 3600)
    m, sec = divmod(rem, 60)
    dec_seconds = round(abs(dec_deg)*3600)
    d, rem = divmod(dec_seconds, 3600)
    dm, ds = divmod(rem, 60)
    sign = "-" if math.copysign(1, dec_deg) < 0 else "+"
    return (f":Sr{h:02d}:{m:02d}:{sec:02d}#",
            f":Sd{sign}{d:02d}*{dm:02d}:{ds:02d}#",
            ":MS#")


def angular_error_deg(ra1, dec1, ra2, dec2):
    a, b = math.radians(dec1), math.radians(dec2)
    x = (math.sin(a)*math.sin(b) +
         math.cos(a)*math.cos(b)*math.cos(math.radians(ra1-ra2)))
    return math.degrees(math.acos(max(-1, min(1, x))))
