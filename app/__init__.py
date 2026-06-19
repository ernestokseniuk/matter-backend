import os
import re

from flask import Flask, request

from .controller import load_controller_with_status
from .routes import api
from .storage import DeviceRepository


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    database_path = os.getenv("DATABASE_PATH", "data/matter_hub.sqlite3")
    app.config.from_mapping(
        SECRET_KEY="matter-hub-secret",
        DATABASE_PATH=database_path,
    )

    repository = DeviceRepository(app.config["DATABASE_PATH"])
    repository.initialize()
    app.extensions["device_repository"] = repository
    controller, controller_error = load_controller_with_status()
    app.extensions["matter_controller"] = controller
    app.extensions["matter_controller_error"] = controller_error

    def _is_allowed_origin(origin: str | None) -> bool:
        if not origin:
            return False
        origin = origin.strip()
        if os.getenv("CORS_ALLOW_ALL") == "1":
            return True
        static_allowed = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
        ).split(",")
        if origin in [item.strip() for item in static_allowed if item.strip()]:
            return True
        return bool(re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$", origin, re.IGNORECASE))

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if _is_allowed_origin(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Accept"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "86400"
        return response

    @app.before_request
    def handle_preflight():
        if request.method != "OPTIONS":
            return None
        response = app.make_default_options_response()
        return add_cors_headers(response)

    app.register_blueprint(api)
    return app