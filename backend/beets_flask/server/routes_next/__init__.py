from quart import Blueprint, Quart

from .beets import beets_bp

api_bp = Blueprint("api_v1", __name__, url_prefix="/api_v1")
api_bp.register_blueprint(beets_bp)


def register_routes(app: Quart):

    app.register_blueprint(api_bp)
