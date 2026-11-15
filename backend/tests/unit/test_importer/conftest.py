import logging
import shutil
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
