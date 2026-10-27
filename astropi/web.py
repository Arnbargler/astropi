"""Flask API. Requests never call the camera SDK directly."""
from queue import Full
from flask import Flask, abort, jsonify, make_response, render_template, request
from .camera.worker import CameraWorker
from .config import Settings
from .control import ControlLease
from .status import snapshot


def create_app(settings: Settings | None = None, camera=None, lease=None) -> Flask:
    app = Flask(__name__)
    config = settings if settings is not None else Settings.from_environment()
    worker = camera if camera is not None else CameraWorker()
    control = lease if lease is not None else ControlLease()

    def require_operator():
        if not control.owns(request.headers.get("X-AstroPi-Control", "")):
            abort(403, description="Use Take Control to change camera settings")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        data = snapshot(config)
        data["mode"] = "camera_preview_development"
        camera_state = worker.status()
        data["camera"].update(camera_state)
        data["camera"]["sdk_connected"] = camera_state["phase"] in ("running", "stopping")
        data["controller_held"] = control.held()
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
        return jsonify(ok=True)

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
        except Full:
            return jsonify(error="Camera command queue is full"), 429
        return jsonify(ok=True, request_id=request_id), 202

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

    @app.get("/api/camera/progress")
    def camera_progress():
        # Cheap polling path; avoids findmnt and USB scans on every frame check.
        return jsonify(worker.status())

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
