"""Prepare music library albums for submission to the MusicBrainz release editor.

The MusicBrainz web service does not support creating new releases via the API,
so this module collects everything needed (title, artist, tracks, ISRCs, barcode,
label, ...) to fill the release editor at musicbrainz.org/release/add manually.
"""

from quart import Blueprint, g

from beets_flask.config import get_config

from .resources import resources_bp

musicbrainz_bp = Blueprint("musicbrainz", __name__, url_prefix="/musicbrainz")
musicbrainz_bp.register_blueprint(resources_bp)

from typing import TYPE_CHECKING  # noqa: E402

from beets.ui import _open_library  # noqa: E402

if TYPE_CHECKING:
    from beets.library import Library
    from quart.ctx import _AppCtxGlobals

    class LibraryCtx(_AppCtxGlobals):
        lib: Library

    g = LibraryCtx()


@musicbrainz_bp.before_request
async def attach_library():
    """Attach the library to the global object.

    This allows to reuse an open library for each request in the same thread.
    """
    config = get_config()
    # we will need to see if keeping the db open from each thread is what we want,
    # the importer may want to write.
    if not hasattr(g, "lib") or g.lib is None:
        g.lib = _open_library(config)
    else:
        if str(g.lib.path) != str(config.as_path()):
            g.lib = _open_library(config)


__all__ = ["musicbrainz_bp"]
