"""Flask application — API Gateway + Clarity API mount."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.clarity_api.routes import bp as clarity_bp  # noqa: E402
from server.gateway.middleware import bind_request_context, request_id  # noqa: E402
from server.services.env_config import load_dotenv  # noqa: E402


def create_app() -> Flask:
    load_dotenv()
    app = Flask(__name__)

    @app.before_request
    def _gateway_before():
        bind_request_context(request)
        if request.method == "OPTIONS":
            return ("", 204)

    @app.after_request
    def _gateway_after(response):
        rid = request_id()
        if rid:
            response.headers["X-Request-Id"] = rid
        # Prototype CORS for Vite
        response.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "*"
        )
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Customer-Id, X-Request-Id"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, OPTIONS"
        response.headers["Access-Control-Expose-Headers"] = "X-Request-Id"
        return response

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "clarity-api"})

    app.register_blueprint(clarity_bp, url_prefix="/api")
    return app


def main() -> None:
    app = create_app()
    # CLARITY_PORT / CLARITY_DEBUG let e2e runs start an isolated instance.
    port = int(os.environ.get("CLARITY_PORT") or 8787)
    debug = os.environ.get("CLARITY_DEBUG", "1") == "1"
    # SQLite + Flask reloader = two processes fighting for the DB → 500 "database is locked".
    app.run(host="127.0.0.1", port=port, debug=debug, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
