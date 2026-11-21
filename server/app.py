"""DARKPRIME Flask application factory."""
from __future__ import annotations

import sys

from flask import Flask, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from . import config
from .api import bp as api_bp
from .dashboard import bp as dashboard_bp
from .db import close_db


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(config.load_config())
    if overrides:
        app.config.update(overrides)
    if app.config["REQUIRE_HTTPS"] and (
        str(app.config["SECRET_KEY"]).startswith("dev-only-")
        or str(app.config["TOKEN_PEPPER"]).startswith("dev-only-")
    ):
        raise RuntimeError("Set DARKPRIME_SECRET_KEY and DARKPRIME_TOKEN_PEPPER before production use.")
    app.register_blueprint(api_bp)
    app.register_blueprint(dashboard_bp)
    app.teardown_appcontext(close_db)

    if app.config["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.before_request
    def require_https():
        if app.config["REQUIRE_HTTPS"] and not request.is_secure:
            return jsonify(error="https_required"), 403
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    if app.config["SECRET_KEY"].startswith("dev-only-") and not app.config["REQUIRE_HTTPS"]:
        print("WARNING: DARKPRIME is using development secrets. Set DARKPRIME_SECRET_KEY and "
              "DARKPRIME_TOKEN_PEPPER before exposing this service.", file=sys.stderr)

    return app
