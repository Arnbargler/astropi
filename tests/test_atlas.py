"""Offline atlas assets, catalogue invariants and safe Flask integration."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "astropi/static/vendor/virtualsky"


def test_all_110_messier_targets_are_local_and_valid():
    entries = json.loads((VENDOR / "messier.json").read_text())
    assert len(entries) == 110
    by_name = {item["target"]["name"]: item for item in entries}
    assert set(by_name) == {f"M{n}" for n in range(1, 111)}
    for item in entries:
        assert 0 <= item["ra"]["decimal"] < 360
        assert -90 <= item["dec"]["decimal"] <= 90


def test_virtualsky_dependencies_are_vendored_for_offline_use():
    for filename in (
        "stuquery.min.js", "virtualsky.min.js", "virtualsky-planets.js",
        "stars.json", "lines_latin.json", "lang/en.json", "messier.json",
    ):
        assert (VENDOR / filename).stat().st_size > 100
    html = (ROOT / "astropi/templates/index.html").read_text()
    for file in ("stuquery.min.js", "virtualsky.min.js"):
        assert f"vendor/virtualsky/{file}" in html
    assert "coordinates.js" in html and "atlas.js" in html
    assert html.index("coordinates.js") < html.index("atlas.js")
    assert "id=\"atlas-target-readout\"" in html
    assert 'id="atlas-goto"' in html
    assert '<button type="button" id="atlas-goto" disabled' in html
    assert "id=\"atlas-sky\"" in html
    assert "id=\"panel-find\"" in html
    assert "id=\"mount-stop\"" in html
    assert html.index('id="mount-stop"') < html.index('id="panel-find"')
    assert "http://" not in html and "https://" not in html


def test_atlas_never_calls_motion_or_online_target_lookup():
    code = (ROOT / "astropi/static/atlas.js").read_text()
    assert '"/api/status"' in code
    assert '"/static/vendor/virtualsky/messier.json"' in code
    assert "45.2933" in code and "-75.8571" in code
    assert 'window.S.virtualsky' in code
    assert "sky.addPointer" in code
    for forbidden in ("/api/mount/", "strudel.org", "wikisky.org", "sky-map.org", "navigator.geolocation"):
        assert forbidden not in code

def test_geometric_position_module_is_offline_and_read_only():
    code = (ROOT / "astropi/static/coordinates.js").read_text()
    assert "precessJ2000" in code and "altitudeDeg" in code
    assert "azimuthDeg" in code
    assert "fetch(" not in code and "/api/mount/" not in code
    adapter = (ROOT / "astropi/static/atlas.js").read_text()
    assert "AstroPiCoordinates.position" in adapter
    assert "atlas-visibility" in adapter
