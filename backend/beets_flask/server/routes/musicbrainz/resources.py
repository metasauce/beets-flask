from __future__ import annotations

from typing import TYPE_CHECKING

from quart import Blueprint, g, jsonify, request

from beets_flask.config import get_config
from beets_flask.server.exceptions import NotFoundException
from beets_flask.server.routes.exception import InvalidUsageException

from .mb import search_artist, search_release_by_barcode
from .prepare import prepare_release

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g

resources_bp = Blueprint("musicbrainz_resources", __name__)

__all__ = ["resources_bp"]


def _editor_url() -> str:
    """Url of the MusicBrainz release editor, configurable for mirrors."""
    config = get_config()
    return config["gui"]["musicbrainz"]["editor_url"].get(str)  # type: ignore


def _ws_url() -> str:
    """Base url of the MusicBrainz web service, configurable for mirrors."""
    config = get_config()
    return config["gui"]["musicbrainz"]["ws_url"].get(str)  # type: ignore


def _check_artists_enabled() -> bool:
    """Whether the artist lookup against the MusicBrainz web service is on."""
    config = get_config()
    return bool(config["gui"]["musicbrainz"]["check_artists"].get(bool))  # type: ignore


@resources_bp.route("/status", methods=["GET"])
async def status():
    """Check whether the musicbrainz assistant is available."""
    return jsonify(
        {
            "enabled": True,
            "editor_url": _editor_url(),
            "ws_url": _ws_url(),
            "check_artists": _check_artists_enabled(),
        }
    )


@resources_bp.route("/prepare", methods=["POST"])
async def prepare():
    """Prepare a beets album for submission to the MusicBrainz release editor.

    Expects a JSON body with an ``albumId`` (int) pointing to an album in the
    beets library.
    """
    data = await request.get_json(force=True, silent=True) or {}
    album_id = data.get("albumId")
    if not isinstance(album_id, int):
        raise InvalidUsageException(
            'Invalid request body, expected: {"albumId": <int>}'
        )

    album = g.lib.get_album(album_id)
    if not album:
        raise NotFoundException(
            f"Album with beets_id:'{album_id}' not found in beets db."
        )

    on_musicbrainz = None
    if not (album.mb_albumid or "").strip():
        barcode = (album.barcode or "").strip()
        if barcode:
            on_musicbrainz = _barcode_match(barcode) is not None

    return jsonify(
        prepare_release(
            album,
            _editor_url(),
            lookup=search_artist,
            on_musicbrainz=on_musicbrainz,
        )
    )


#: Minimum search score for a barcode lookup to count as a match.
_MATCH_SCORE_THRESHOLD = 80


def _barcode_match(barcode: str) -> str | None:
    """MBID of the release group matching a barcode, or None."""
    matches = search_release_by_barcode(barcode)
    if matches and matches[0].get("score", 0) >= _MATCH_SCORE_THRESHOLD:
        return matches[0]["mbid"]
    return None


@resources_bp.route("/album_exists/<int:album_id>", methods=["GET"])
async def album_exists(album_id: int):
    """Whether an album from the beets library is on MusicBrainz.

    Albums with a stored ``mb_albumid`` are reported as present without
    hitting the web service. Otherwise the release is looked up by barcode,
    which identifies an album precisely.
    """
    album = g.lib.get_album(album_id)
    if not album:
        raise NotFoundException(
            f"Album with beets_id:'{album_id}' not found in beets db."
        )

    if album.mb_albumid:
        return jsonify(
            {"album_id": album_id, "exists": True, "mbid": album.mb_albumid}
        )

    barcode = (album.barcode or "").strip()
    mbid = _barcode_match(barcode) if barcode else None
    return jsonify(
        {"album_id": album_id, "exists": mbid is not None, "mbid": mbid}
    )
