from typing import TYPE_CHECKING

from beets.ui import _open_library
from quart import Blueprint, g

from beets_flask.config.beets_config import get_config

from .albums import albums_bp
from .items import items_bp

if TYPE_CHECKING:
    from beets.library import Library
    from quart.ctx import _AppCtxGlobals

    class LibraryCtx(_AppCtxGlobals):
        lib: Library

    g = LibraryCtx()


beets_bp = Blueprint("beets", __name__, url_prefix="/beets")

beets_bp.register_blueprint(items_bp)
beets_bp.register_blueprint(albums_bp)


@beets_bp.before_request
async def attach_library():
    """Attach the library to the global object.

    This allows to reuse an open library for each request in the same thread.
    """
    # we will need to see if keeping the db open from each thread is what we want,
    # the importer may want to write.
    if not hasattr(g, "lib") or g.lib is None:
        config = get_config().beets_config
        g.lib = _open_library(config)
