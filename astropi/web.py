"""Read-only routes; never performs hardware operations."""
from flask import Flask, jsonify, render_template
from .config import Settings
from .status import snapshot

def create_app(settings: Settings | None = None) -> Flask:
    app = Flask(__name__)
    config = settings if settings is not None else Settings.from_environment()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        return jsonify(snapshot(config))

    return app
