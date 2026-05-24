"""Get metadata for a library item.

TODO: Allow to modify metadata or let ppl apply beets changes for a library item.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

from quart import Blueprint, g
from tinytag import TinyTag

from beets_flask.server.exceptions import IntegrityException, NotFoundException
from beets_flask.server.routes.library.path_utils import resolve_library_path

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g


metadata_bp = Blueprint("metadata", __name__)


__all__ = ["metadata_bp"]


@metadata_bp.route("/item/<int:item_id>/metadata", methods=["GET"])
async def item_metadata(item_id: int):
    # Item from beets library
    # FIXME: The following should be made into a common function
    # it is also used in artwork.py
    item = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:'{item_id}' not found in beets db."
        )

    # File path
    item_path = resolve_library_path(item.path)
    if not os.path.exists(item_path):
        raise IntegrityException(
            f"Item file '{item_path}' does not exist for item beets_id:'{item_id}'."
        )

    return _get_metadata(item_path)


@metadata_bp.route("/file/<string:filepath>/metadata", methods=["GET"])
async def file_metadata(filepath: str):
    """Get metadata for a file given its path.

    It is hard to encode file paths with special characters in URLs so we use
    hex here and decode it back.
    """
    filepath = bytes.fromhex(filepath).decode("utf-8")

    if not os.path.exists(filepath):
        raise NotFoundException(f"File '{filepath}' does not exist.")

    return _get_metadata(filepath)


def _get_metadata(file: str | Path):
    """Get the file metadata for a given audio file."""
    tags = TinyTag.get(file).as_dict()

    # Only include name in filename
    tags["filename"] = os.path.basename(file)
    return tags
