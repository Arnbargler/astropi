"""Flask API. Requests never call the camera SDK directly."""
from flask import Flask, abort, jsonify, make_response, render_template, request
from .camera.worker import CameraWorker
from .capture.manager import CaptureManager, CaptureBusy
from .capture.formats import validate_formats
from .capture.storage import CaptureStorage, StorageError
from .config import Settings
from .mount.worker import MountWorker
from .control import ControlLease
from .status import snapshot


def create_app(settings: Settings | None = None, camera=None, lease=None, mount=None) -> Flask:
    app = Flask(__name__)
    config = settings if settings is not None else Settings.from_environment()
    worker = camera if camera is not None else CameraWorker(
        capture=CaptureManager(CaptureStorage(config))
    )
    control = lease if lease is not None else ControlLease()
    mount_worker = mount if mount is not None else MountWorker(config.mount_serial)

    def require_operator():
        if not control.owns(request.headers.get("X-AstroPi-Control", "")):
            abort(403, description="Use Take Control for camera or mount operations")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        data = snapshot(config)
        camera_state = worker.status()
        data["camera"].update(camera_state)
        data["camera"]["sdk_connected"] = camera_state["phase"] in ("running", "stopping")
        data["mount"].update(mount_worker.status())
        data["controller_held"] = control.held()
        data["capture"] = worker.capture_status()
        return jsonify(data)

    @app.post("/api/control/take")
    def take():
        token = control.take()
        if token is None:
            return jsonify(error="Another browser currently controls AstroPi"), 423
        return jsonify(token=token)

    @app.post("/api/control/heartbeat")
    def heartbeat():
        if not control.renew(request.headers.get("X-AstroPi-Control", "")):
            return jsonify(error="Operator lease expired"), 403
        return jsonify(ok=True)

    @app.post("/api/control/release")
    def release():
        if not control.release(request.headers.get("X-AstroPi-Control", "")):
            return jsonify(error="Not the current operator"), 403
        # A release can never leave an active manual movement authorized.
        try:
            if mount_worker.status().get("motion_phase") in ("starting", "moving", "goto_queued", "goto_slewing", "home_queued", "home_slewing"):
                mount_worker.emergency_stop("Operator released control")
        except RuntimeError:
            pass
        return jsonify(ok=True)

    @app.post("/api/mount/connect")
    def connect_mount():
        require_operator()
        if not mount_worker.connect():
            return jsonify(error="Mount connection worker already active"), 409
        return jsonify(ok=True), 202

    @app.post("/api/mount/disconnect")
    def disconnect_mount():
        require_operator()
        if not mount_worker.disconnect():
            return jsonify(error="Mount connection worker is not active"), 409
        return jsonify(ok=True), 202

    @app.post("/api/mount/jog")
    def mount_jog():
        require_operator()
        payload = request.get_json(silent=True) or {}
        try:
            direction = mount_worker.jog(
                payload.get("direction"), speed=payload.get("speed", "slow")
            )
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, direction=direction), 202

    @app.post("/api/mount/goto")
    def mount_goto():
        require_operator()
        payload = request.get_json(silent=True) or {}
        try:
            target = mount_worker.goto(payload.get("target"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, target=target, state="queued"), 202

    @app.post("/api/mount/jog-heartbeat")
    def mount_jog_heartbeat():
        require_operator()
        payload = request.get_json(silent=True) or {}
        try:
            mount_worker.heartbeat(payload.get("direction"))
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True)

    @app.post("/api/mount/stop")
    def mount_emergency_stop():
        # Safety action intentionally does NOT require operator ownership.
        # A viewer may request Stop, but can never start a manual slew.
        try:
            mount_worker.emergency_stop()
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, state="stop_requested"), 202

    @app.post("/api/mount/environment/read")
    def read_mount_environment():
        require_operator()
        try:
            mount_worker.request_environment_read()
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, state="queued"), 202

    @app.post("/api/mount/environment/sync")
    def sync_mount_time_site():
        require_operator()
        try:
            mount_worker.request_time_site_sync()
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, state="queued"), 202

    @app.post("/api/mount/tracking")
    def set_mount_tracking():
        require_operator()
        payload = request.get_json(silent=True) or {}
        try:
            enabled = mount_worker.request_tracking(payload.get("enabled"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, enabled=enabled, state="queued"), 202

    @app.post("/api/mount/az-home")
    def mount_az_home():
        require_operator()
        try:
            state = mount_worker.az_home()
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, state=state), 202

    @app.post("/api/mount/north-level")
    def set_north_level():
        """Record operator-confirmed physical setup; never move or sync mount."""
        require_operator()
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Expected JSON object with confirmed boolean"), 400
        try:
            confirmed = mount_worker.confirm_north_level(payload.get("confirmed"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, confirmed=confirmed), 200

    @app.get("/api/mount/status")
    def mount_status():
        return jsonify(mount_worker.status())

    @app.post("/api/camera/start")
    def start_camera():
        require_operator()
        if not worker.start():
            return jsonify(error="Camera worker already active"), 409
        return jsonify(ok=True), 202

    @app.post("/api/camera/stop")
    def stop_camera():
        require_operator()
        if not worker.stop():
            return jsonify(error="Camera worker not running"), 409
        return jsonify(ok=True), 202

    @app.post("/api/camera/settings")
    def set_settings():
        require_operator()
        payload = request.get_json(silent=True) or {}
        try:
            request_id = worker.configure(payload.get("gain"), payload.get("exposure_us"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, request_id=request_id), 202

    @app.post("/api/camera/binning")
    def camera_binning():
        require_operator()
        payload = request.get_json(silent=True) or {}
        try:
            binning = worker.set_binning(payload.get("binning"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, binning=binning), 202

    @app.post("/api/camera/preview-mode")
    def camera_preview_mode():
        require_operator()
        payload = request.get_json(silent=True) or {}
        try:
            mode = worker.set_preview_mode(payload.get("mode"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(ok=True, mode=mode)

    @app.post("/api/camera/debayer")
    def camera_debayer():
        require_operator()
        payload = request.get_json(silent=True) or {}
        try:
            enabled = worker.set_debayer(payload.get("enabled"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(ok=True, enabled=enabled)

    @app.post("/api/capture")
    def capture():
        require_operator()
        body = request.get_json(silent=True) or {}
        try:
            formats = validate_formats(body.get("formats"))
            capture_id = worker.request_capture(list(formats))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except CaptureBusy as exc:
            return jsonify(error=str(exc)), 409
        except StorageError as exc:
            return jsonify(error=str(exc)), 503
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, id=capture_id), 202

    @app.post("/api/capture/sequence")
    def sequence():
        require_operator()
        payload = request.get_json(silent=True) or {}
        try:
            formats = validate_formats(payload.get("formats"))
            count = payload.get("count")
            if type(count) is not int or not 2 <= count <= CaptureManager.MAX_FRAMES:
                return jsonify(error=f"Sequence count must be an integer from 2 to {CaptureManager.MAX_FRAMES}"), 400
            capture_id = worker.request_capture(list(formats), count=count)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except CaptureBusy as exc:
            return jsonify(error=str(exc)), 409
        except StorageError as exc:
            return jsonify(error=str(exc)), 503
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, id=capture_id, count=count), 202

    @app.post("/api/capture/cancel")
    def cancel_sequence():
        require_operator()
        try:
            capture_id = worker.cancel_capture()
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, id=capture_id), 202

    @app.get("/api/capture/status")
    def capture_status():
        return jsonify(worker.capture_status())

    @app.get("/api/camera/progress")
    def camera_progress():
        # Cheap polling path; avoids findmnt and USB scans on every frame check.
        data = worker.status()
        data["capture"] = worker.capture_status()
        return jsonify(data)

    @app.get("/api/camera/frame.jpg")
    def frame():
        jpeg, number = worker.frame()
        if jpeg is None:
            return jsonify(error="No camera preview frame yet"), 503
        response = make_response(jpeg)
        response.headers["Content-Type"] = "image/jpeg"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Number"] = str(number)
        return response

    return app
