from quart import Blueprint

from .albums import albums_bp
from .items import items_bp

beets_bp = Blueprint("beets", __name__, url_prefix="/beets")

beets_bp.register_blueprint(items_bp)
beets_bp.register_blueprint(albums_bp)
