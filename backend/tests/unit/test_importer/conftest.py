import atexit
import logging
import shutil
import tempfile
from pathlib import Path

import pytest

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


VALID_PATHS = ["1991", "1991/Chant [SINGLE]", "Annix", "Annix/Antidote"]


# Path relative to data/audio
@pytest.fixture
def album_paths(tmpdir_factory):
    # Create a temporary directory
    tmpdir = tmpdir_factory.mktemp("audio")

    destinations = []

    for path in VALID_PATHS:
        # Copy files
        source = album_path_absolute(path)
        destination = tmpdir / path
        # os.makedirs(destination, exist_ok=True)

        shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(source, destination)
        destinations.append(Path(destination))

    yield destinations

    # Clean up
    shutil.rmtree(tmpdir)


def album_path_absolute(path: str):
    return Path(__file__).parent.parent.parent / "data" / "audio" / path


def valid_data_for_album_path(path: str | Path) -> dict:
    """Return (a limited subset of) valid tag data for an album path."""
    if isinstance(path, Path):
        p = path
    else:
        p = album_path_absolute(path)

    if p.name in ["1991", "Chant [SINGLE]"]:
        return {
            "match_url": "https://musicbrainz.org/release/b0219c84-9277-4fdc-b054-aae4aae3dbbf",
            "match_album": "Chant",
            "match_artist": "1991",
            "num_tracks": 1,
            "album_folder_basename": p.name,
            "distance": 0.05714285714285714,
        }
    elif p.name in ["Annix", "Antidote"]:
        return {
            "match_url": "https://musicbrainz.org/release/a25664c1-6db7-43db-9e32-1f1f249dbecc",
            "match_album": "Antidote",
            "match_artist": "Annix",
            "num_tracks": 1,
            "album_folder_basename": p.name,
            "distance": 0.08888888888888889,
        }
    else:
        raise NotImplementedError(f"Unknown test album path {p=}")


# ----------------- Monkeypath beets to use cached responses ----------------- #

import hashlib
import pickle

from beets import autotag
from beets.autotag import tag_album as _tag_album

album_path: str
lookup_cache_dir: Path


def use_mock_tag_album(a_dir: str):
    """Use a cached lookup for the tag_album function in beets
    this allows to not make requests to the internet when testing
    the importer.
    """
    global album_path, lookup_cache_dir
    album_path = a_dir

    # Create temp lookup cache directory
    lookup_cache_dir = Path(tempfile.mkdtemp(prefix="beets_lookup_cache_"))
    atexit.register(shutil.rmtree, lookup_cache_dir, ignore_errors=True)

    autotag.tag_album = tag_album


def tag_album(
    items,
    search_artist: str | None = None,
    search_name: str | None = None,
    search_ids: list[str] = [],
):
    global album_path
    log.debug(f"Using monkey patched lookup {album_path=}")

    # Compute items hash based on the items
    m = hashlib.md5()
    for item in items:
        m.update(item.path)
    if search_artist:
        m.update(search_artist.encode("utf-8"))
    if search_name:
        m.update(search_name.encode("utf-8"))
    for search_id in search_ids:
        m.update(search_id.encode("utf-8"))
    items_hash = m.hexdigest()[:8]

    cache_file = lookup_cache_dir / f"lookup_{items_hash}.pickle"

    if cache_file.exists():
        log.debug(f"Using cached lookup from temp dir {cache_file}")
        with open(cache_file, "rb") as f:
            return pickle.load(f)
    else:
        # TODO: This pickle contains absolute paths to the files
        # while undesired (no use in having them in the git repo) its for now the
        # easiest way... and we hope music brainz does not change its data too often!
        log.debug(f"Using default lookup {album_path=}")
        res = _tag_album(items, search_artist, search_name, search_ids)

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "wb") as f:
            pickle.dump(res, f)

        return res


autotag.tag_album = tag_album
