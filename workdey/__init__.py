"""WorkDey Smart Match & Apply engine."""

from __future__ import annotations

from pathlib import Path

from flask import Flask
from flask_cors import CORS

from config import Config
from workdey.db import db


def create_app(config_object: type = Config) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )
    app.config.from_object(config_object)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})

    from workdey import models  # noqa: F401
    from workdey.routes_auth import auth_bp
    from workdey.routes_app import app_bp
    from workdey.routes_ops import ops_bp
    from workdey.routes_public import public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(app_bp, url_prefix="/api")
    app.register_blueprint(ops_bp, url_prefix="/api/ops")

    with app.app_context():
        db.create_all()
        from workdey.seed import seed_if_needed

        seed_if_needed()

    return app
