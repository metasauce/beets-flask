from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote

from beets.library import Album
from quart import Blueprint, g, jsonify, request

from beets_flask.config import get_config
from beets_flask.database.models.states import SessionStateInDb
from beets_flask.disk import Archive, File, Folder, fs_item_from_path
from beets_flask.importer.states import TaskState
from beets_flask.server.exceptions import NotFoundException
from beets_flask.server.routes.exception import InvalidUsageException
from beets_flask.utility import AUDIO_EXTENSIONS
from beets_flask.watchdog.inbox import get_inbox_folders

from .mb import search_artist, search_release_by_barcode
from .prepare import _album_from_task, _match_mbid, prepare_release

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


def _strong_rec_thresh() -> float:
    """Distance below which a match is considered the same release."""
    return float(get_config()["match"]["strong_rec_thresh"].get(float))  # type: ignore


def _inbox_album_folders() -> list[Folder | Archive]:
    """All album folders currently in the inbox, deduplicated."""
    folders: list[Folder | Archive] = []
    seen: set[str] = set()
    for inbox in get_inbox_folders():
        try:
            root = Folder.from_path(inbox, subdirs=False)
        except (FileNotFoundError, NotADirectoryError):
            continue
        for item in root.walk():
            if not isinstance(item, (Folder, Archive)) or not item.is_album:
                continue
            if item.full_path in seen:
                continue
            seen.add(item.full_path)
            folders.append(item)
    return folders


def _folder_task(folder: Folder | Archive) -> TaskState | None:
    """First task of the most recent session for a folder, or None.

    The session is resolved and materialized within a single database session,
    so its lazy-loaded relationships (e.g. the folder) can be accessed.
    """
    from beets_flask.database import db_session_factory

    with db_session_factory() as dbs:
        session = SessionStateInDb.get_by_hash_and_path(
            folder.hash, folder.full_path, db_session=dbs
        )
        if session is None:
            return None
        live = session.to_live_state(False)
        return live.task_states[0] if live.task_states else None


def _session_summary(folder: Folder | Archive, task: TaskState | None) -> dict:
    """Summary of an inbox album, using the match of its import session."""
    meta = task.current_metadata if task is not None else None
    best = task.best_candidate_state if task is not None else None

    name = meta.get("album") if meta else None
    artist = (meta.get("albumartist") or meta.get("artist")) if meta else None
    year = meta.get("year") if meta else None

    match_percentage: float | None = None
    match_mbid: str | None = None
    if best is not None:
        match_percentage = round((1 - best.distance.distance) * 100, 1)
        match_mbid = _match_mbid(best.match)
        name = name or best.album
        artist = artist or best.artist

    return {
        "folder_path": folder.full_path,
        "folder_hash": folder.hash,
        "type": folder.type,
        "name": name,
        "albumartist": artist,
        "year": year,
        "match_percentage": match_percentage,
        "match_mbid": match_mbid,
        "has_session": task is not None,
        "has_match": best is not None,
    }


def _restore_leading_slash(folder_path: str) -> str:
    """The ``<path:>`` converter strips the leading slash; put it back."""
    if folder_path and not folder_path.startswith("/"):
        return "/" + folder_path
    return folder_path


def _inbox_album_folder(folder_path: str) -> Folder | Archive:
    """Resolve an inbox path to an album folder/archive."""
    if not Path(folder_path).is_absolute():
        raise InvalidUsageException(
            f"Only absolute paths are allowed. Got: {folder_path=}"
        )
    try:
        folder = fs_item_from_path(folder_path, subdirs=False)
    except (FileNotFoundError, NotADirectoryError):
        raise NotFoundException(f"Folder '{folder_path}' not found on disk.")
    if not isinstance(folder, (Folder, Archive)) or not folder.is_album:
        raise NotFoundException(f"'{folder_path}' is not an album folder.")
    return folder


def _album_from_files(folder: Folder | Archive) -> Album:
    """Build a synthetic Album from the tags of the audio files on disk."""
    from beets.library import Item
    from beets.util import get_most_common_tags

    items: list[Item] = []
    stack: list[Folder] = [folder] if isinstance(folder, Folder) else []
    while stack:
        node = stack.pop()
        for child in node.children:
            if isinstance(child, Folder):
                stack.append(child)
            elif isinstance(child, File):
                suffix = Path(child.full_path).suffix.lstrip(".").lower()
                if suffix in AUDIO_EXTENSIONS:
                    items.append(Item.from_path(child.full_path))

    if not items:
        raise NotFoundException(f"No audio files found in folder '{folder.full_path}'.")

    likelies, _ = get_most_common_tags(items)
    metadata = {k: v for k, v in likelies.items() if v not in (None, "")}
    album = Album(None, **metadata)
    object.__setattr__(album, "items", lambda: items)
    return album


@resources_bp.route("/albums", methods=["GET"])
async def albums():
    """All albums currently in the inbox, with their MusicBrainz match info.

    The match percentage of each album comes from the most recent import
    session of its folder (i.e. the quality of the best candidate match).
    """
    out = []
    for folder in _inbox_album_folders():
        task = _folder_task(folder)
        out.append(_session_summary(folder, task))
    return jsonify(out)


@resources_bp.route("/prepare/<path:folder_path>", methods=["GET"])
async def prepare_folder(folder_path: str):
    """Prepare an inbox album for submission to the MusicBrainz release editor.

    Uses the album's import session (its best candidate match) when present,
    otherwise falls back to reading the tags of the music files directly.

    The path arrives percent-encoded (slashes as ``%2F``, which Werkzeug does
    not decode inside the ``<path:>`` converter) and is decoded here. The
    ``<path:>`` converter also strips the leading slash, so it is restored.
    """
    folder = _inbox_album_folder(_restore_leading_slash(unquote(folder_path)))
    task = _folder_task(folder)

    album = _album_from_task(task) if task is not None else _album_from_files(folder)

    on_musicbrainz: bool | None = None
    best = task.best_candidate_state if task is not None else None
    if best is not None:
        on_musicbrainz = best.distance.distance <= _strong_rec_thresh()
    elif album.mb_albumid:
        on_musicbrainz = True

    prepared = prepare_release(
        album,
        _editor_url(),
        lookup=search_artist,
        on_musicbrainz=on_musicbrainz,
    )
    prepared["folder_path"] = folder.full_path
    return jsonify(prepared)


@resources_bp.route("/album_exists/<path:folder_path>", methods=["GET"])
async def album_exists_inbox(folder_path: str):
    """Whether an inbox album is on MusicBrainz.

    An album whose best match is close enough to be auto-imported is reported
    as present. Otherwise the release is looked up by barcode, which
    identifies an album precisely.
    """
    folder = _inbox_album_folder(_restore_leading_slash(unquote(folder_path)))
    task = _folder_task(folder)
    best = task.best_candidate_state if task is not None else None

    if best is not None and best.distance.distance <= _strong_rec_thresh():
        mbid = _match_mbid(best.match)
        return jsonify({"folder_path": folder.full_path, "exists": True, "mbid": mbid})

    barcode = None
    if task is not None:
        barcode = task.current_metadata.get("barcode")
    if not barcode:
        album = _album_from_files(folder)
        barcode = album.barcode
    barcode = (barcode or "").strip()
    mbid = _barcode_match(barcode) if barcode else None
    return jsonify(
        {
            "folder_path": folder.full_path,
            "exists": mbid is not None,
            "mbid": mbid,
        }
    )


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
        return jsonify({"album_id": album_id, "exists": True, "mbid": album.mb_albumid})

    barcode = (album.barcode or "").strip()
    mbid = _barcode_match(barcode) if barcode else None
    return jsonify({"album_id": album_id, "exists": mbid is not None, "mbid": mbid})
