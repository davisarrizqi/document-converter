"""HTTP routes. They parse the request, call a service, and map the response."""

from flask import Flask, jsonify

from app.version import __version__
from app.routes.conversions import conversions_bp
from app.routes.documents import documents_bp
from app.routes.health import health_bp
from app.routes.web import web_bp


def register_blueprints(app: Flask) -> None:
    @app.get("/")
    def service_index():
        return jsonify(
            {
                "data": {
                    "name": "document-converter",
                    "version": __version__,
                    "resources": {
                        "health": "/api/v1/health",
                        "documents": "/api/v1/documents",
                        "conversions": "/api/v1/conversions",
                        "convert": "/api/v1/convert",
                        "debug": "/web/debug",
                    },
                }
            }
        )

    app.register_blueprint(health_bp, url_prefix="/api/v1")
    app.register_blueprint(documents_bp, url_prefix="/api/v1")
    app.register_blueprint(conversions_bp, url_prefix="/api/v1")
    app.register_blueprint(web_bp, url_prefix="/web")
