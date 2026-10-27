from astropi.config import Settings
from astropi.status import storage_status, usb_present
from astropi.web import create_app

def test_missing_usb_mount_is_never_ready(tmp_path):
    result = storage_status(tmp_path, "expected", is_mount=lambda _: False)
    assert result["ready"] is False
    assert result["state"] == "not_mounted"

def test_wrong_uuid_is_never_ready(tmp_path):
    result = storage_status(tmp_path, "expected", is_mount=lambda _: True, uuid_lookup=lambda _: "wrong")
    assert result["mounted"] is True
    assert result["ready"] is False
    assert result["state"] == "wrong_or_unknown_uuid"

def test_matching_uuid_can_be_ready(tmp_path):
    result = storage_status(tmp_path, "expected", is_mount=lambda _: True, uuid_lookup=lambda _: "expected")
    assert result["ready"] is True
    assert result["free_bytes"] >= 0

def test_usb_ids(tmp_path):
    usb = tmp_path / "dev"
    usb.mkdir()
    (usb / "idVendor").write_text("f266\n")
    (usb / "idProduct").write_text("9a0a\n")
    assert usb_present("f266", "9a0a", tmp_path)
    assert not usb_present("03c3", "4001", tmp_path)

def test_status_endpoint_does_not_initialize_camera_or_mount(tmp_path):
    settings = Settings(tmp_path, "expected", tmp_path / "missing-serial", tmp_path / "missing-usb")
    client = create_app(settings).test_client()
    assert client.get("/").status_code == 200
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["mode"] == "camera_preview_development"
    assert not data["camera"]["sdk_connected"]
    assert not data["mount"]["connected"]
    assert not data["storage"]["ready"]
