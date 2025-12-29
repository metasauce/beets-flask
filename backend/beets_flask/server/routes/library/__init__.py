"""Some wrapper function around the beets library.

Makes it possible to query and expose items to the frontend.
"""

from beets.ui import _open_library
from quart import Blueprint, g

from beets_flask.config import get_config

from .artists import artists_bp
from .artwork import artwork_pb
from .audio import audio_bp
from .metadata import metadata_bp
from .resources import resource_bp
from .stats import stats_bp

library_bp = Blueprint("library", __name__, url_prefix="/library")
library_bp.register_blueprint(artwork_pb)
library_bp.register_blueprint(audio_bp)
library_bp.register_blueprint(resource_bp)
library_bp.register_blueprint(stats_bp)
library_bp.register_blueprint(artists_bp)
library_bp.register_blueprint(metadata_bp)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from beets.library import Library
    from quart.ctx import _AppCtxGlobals

    class LibraryCtx(_AppCtxGlobals):
        lib: Library

    g = LibraryCtx()


@library_bp.before_request
async def attach_library():
    """Attach the library to the global object.

    This allows to reuse an open library for each request in the same thread.
    """
    config = get_config().beets_config
    # we will need to see if keeping the db open from each thread is what we want,
    # the importer may want to write.
    if not hasattr(g, "lib") or g.lib is None:
        g.lib = _open_library(config)
    else:
        if str(g.lib.path) != str(config.as_path()):
            g.lib = _open_library(config)
