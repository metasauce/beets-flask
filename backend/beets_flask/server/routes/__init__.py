from quart import Blueprint, Quart

from .art_preview import art_blueprint
from .config import config_bp
from .db_models import register_state_models
from .exception import error_bp
from .file_upload import file_upload_bp
from .frontend import frontend_bp
from .inbox import inbox_bp
from .library import library_bp
from .monitor import monitor_bp

backend_bp = Blueprint("backend", __name__, url_prefix="/api_v1")

# Register all backend blueprints
backend_bp.register_blueprint(art_blueprint)
backend_bp.register_blueprint(config_bp)
backend_bp.register_blueprint(error_bp)
backend_bp.register_blueprint(file_upload_bp)
backend_bp.register_blueprint(frontend_bp)
backend_bp.register_blueprint(inbox_bp)
backend_bp.register_blueprint(library_bp)
backend_bp.register_blueprint(monitor_bp)


def register_routes(app: Quart):
    # Register database state models
    # to api blueprint i.e. /api_v1/session, /api_v1/task & /api_v1/candidate
    register_state_models(backend_bp)

    app.register_blueprint(backend_bp)
    app.register_blueprint(frontend_bp)


__all__ = ["register_routes"]
