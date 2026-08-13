"""Fetch art via ids.

Allows fetching of art via different ids. At the moment we support:
- Spotify album ids (if spotify plugin is enabled)
"""

import os
from urllib.parse import quote_plus

import aiohttp
from quart import Blueprint, jsonify, redirect, request, url_for

from beets_flask.logger import log
from beets_flask.utility import AUDIO_EXTENSIONS

art_blueprint = Blueprint("art", __name__, url_prefix="/art")


@art_blueprint.route("", methods=["GET"])
async def redirect_external_art():
    """Get Spotify album art."""

    # Check that url query param is set
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "url query param is required."}), 400

    # Check that url is a valid spotify url
    redirect_url: str | None = None
    if "spotify" in url:
        redirect_url = await get_spotify_art(url)
    elif "musicbrainz" in url:
        redirect_url = await get_musicbrainz_art(url)
    elif url.startswith("file://"):
        return await get_folder_art(url)

    if redirect_url:
        return redirect(redirect_url, code=302)
    else:
        return jsonify({"error": "No art found."}), 404


async def get_spotify_art(url: str) -> str | None:
    """Uses spotify oembed to redirect to the album art.

    See https://developer.spotify.com/documentation/embeds/reference/oembed

    Returns the url the the art.
    """
    print(f"https://embed.spotify.com/oembed?url={quote_plus(url)}")
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://embed.spotify.com/oembed?url={quote_plus(url)}"
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("thumbnail_url")
            else:
                log.error(f"Error fetching Spotify art: {response.status}")
                return None


async def get_musicbrainz_art(url: str) -> str | None:
    """Uses musicbrainz oembed to redirect to the album art.

    See https://musicbrainz.org/doc/Cover_Art_Archive/API

    Returns the url the the art.
    """

    # Extract the release id from the url
    # musicbrainz urls look like this:
    # https://musicbrainz.org/release/2b5f7e4d-2a1c-4f6d-8a0c-7b8b9e3a1f3f
    release_id = url.split("/")[-1]

    return f"https://coverartarchive.org/release/{release_id}/front-250"


async def get_folder_art(url: str):
    """Infers the folder art from a given file path.

    This is a bit of a hack, but it works for now.
    url="file:///path/to/music/folder"
    """

    # Check first file for and embedded cover art
    path = url.split("file://")[-1]
    print(path)
    # Check if exists
    if not os.path.exists(path):
        return jsonify({"error": f"Path '{path}' does not exist."}), 404

    # Get first file in folder
    files = [
        f
        for f in os.listdir(path)
        if f.endswith(tuple(["." + e for e in AUDIO_EXTENSIONS]))
    ]
    if not files or len(files) < 1:
        return jsonify({"error": "No audio files found in folder."}), 404

    # Redirect to file art endpoint /file/<filepath>/art
    # filepath must be hex-encoded (see artwork.file_art).
    return redirect(
        url_for(
            "backend.library.artwork.file_art",
            filepath=(path + "/" + files[0]).encode("utf-8").hex(),
        ),
        code=302,
    )
