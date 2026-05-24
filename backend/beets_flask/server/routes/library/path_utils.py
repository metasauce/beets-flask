"""Helpers for resolving paths stored in the beets library.

Beets can store item and artwork paths relative to the configured library
``directory`` when the files live inside that directory.  Beets itself expands
those paths through its library abstractions, but beets-flask sometimes needs a
plain filesystem path for libraries such as mutagen/mediafile, TinyTag, ffmpeg,
or ``os.path.getsize``.

This module provides a single helper that mirrors Beets' expected behavior for
those call sites: absolute paths are returned unchanged; relative paths are
resolved against the currently-open Beets library directory.
"""

import os
from os import PathLike
from typing import TYPE_CHECKING

from beets import util as beets_util
from quart import g

if TYPE_CHECKING:
    from . import g


def resolve_library_path(path: str | bytes | PathLike[str] | PathLike[bytes]) -> str:
    """Return an absolute filesystem path for a Beets item/artwork path.

    Beets commonly stores paths relative to ``Library.directory``.  Directly
    passing such a path to file APIs makes it resolve relative to the current
    process working directory, which is not necessarily the music library root
    inside the beets-flask container.  Resolve relative paths against the
    active Beets library directory so existing Beets databases with relative
    paths work correctly.
    """

    filesystem_path = beets_util.syspath(path)
    if os.path.isabs(filesystem_path):
        return filesystem_path

    lib = getattr(g, "lib", None)
    library_directory = getattr(lib, "directory", None)
    if library_directory:
        return os.path.join(beets_util.syspath(library_directory), filesystem_path)

    return filesystem_path
