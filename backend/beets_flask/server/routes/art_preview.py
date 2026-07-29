"""Fetch art via ids.

Allows fetching of art via different ids. At the moment we support:
- Spotify album ids (if spotify plugin is enabled)
"""

import asyncio
import inspect
import json
import os
import re
import time
from urllib.parse import quote_plus, urlparse

import aiohttp
from beets.plugins import find_plugins
from confuse import ConfigError
from quart import Blueprint, jsonify, make_response, redirect, request, url_for

from beets_flask.config import get_config
from beets_flask.logger import log
from beets_flask.utility import AUDIO_EXTENSIONS

art_blueprint = Blueprint("art", __name__, url_prefix="/art")


@art_blueprint.route("", methods=["GET"])
async def redirect_external_art():
    """Resolve cover art for external release URLs used in preview mode."""

    # Check that url query param is set
    url = request.args.get("url")
    if not url:
        return jsonify({"message": "url query param is required."}), 400

    # Check that url is a valid supported source url
    redirect_url: str | None = None
    if "spotify" in url:
        redirect_url = await get_spotify_art(url)
    elif "musicbrainz" in url:
        redirect_url = await get_musicbrainz_art(url)
    elif "bandcamp" in url:
        redirect_url = await get_bandcamp_art(url)
    elif "discogs" in url:
        redirect_url = await get_discogs_art(url)
    elif "beatport" in url:
        redirect_url = await get_beatport_art(url)
    elif url.startswith("file://"):
        return await get_folder_art(url)

    if redirect_url:
        if redirect_url.startswith("http://") or redirect_url.startswith("https://"):
            return await _proxy_remote_image(redirect_url)
        return redirect(redirect_url, code=302)
    else:
        return jsonify({"error": "No art found."}), 404


async def get_spotify_art(url: str) -> str | None:
    """Uses spotify oembed to redirect to the album art.

    See https://developer.spotify.com/documentation/embeds/reference/oembed

    Returns the url the the art.
    """
    print(f"https://embed.spotify.com/oembed?url={quote_plus(url)}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://embed.spotify.com/oembed?url={quote_plus(url)}"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("thumbnail_url")
                log.error(f"Error fetching Spotify art: {response.status}")
                return None
    except aiohttp.ClientError as err:
        log.error(f"Error fetching Spotify art for {url}: {err}")
        return None


async def get_musicbrainz_art(url: str) -> str | None:
    """Uses musicbrainz oembed to redirect to the album art.

    See https://musicbrainz.org/doc/Cover_Art_Archive/API

    Returns the url the the art.
    """

    # Extract the release id from the url.
    # musicbrainz urls look like this:
    # https://musicbrainz.org/release/2b5f7e4d-2a1c-4f6d-8a0c-7b8b9e3a1f3f
    match = re.search(r"musicbrainz\.org/release/([0-9a-fA-F-]{36})", url)
    if not match:
        return None

    return f"https://coverartarchive.org/release/{match.group(1)}/front-250"


async def _proxy_remote_image(url: str):
    """Fetch and proxy an image URL from the server-side."""
    attempted: list[str] = [url]
    if "coverartarchive.org" in url and "front-250" in url:
        attempted.append(url.replace("front-250", "front"))

    for candidate in attempted:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(candidate) as response:
                    if response.status == 200:
                        content_type = response.headers.get(
                            "Content-Type", "image/jpeg"
                        )
                        if not content_type.startswith("image/"):
                            continue

                        payload = await response.read()
                        resp = await make_response(payload)
                        resp.headers["Content-Type"] = content_type
                        resp.headers["Cache-Control"] = "public, max-age=86400"
                        return resp
        except Exception as err:
            log.error(f"Error proxying image {candidate}: {err}")
            return jsonify({"message": "No artwork found."}), 404

    return jsonify({"message": "No artwork found."}), 404


async def get_bandcamp_art(url: str) -> str | None:
    """Resolve cover art for Bandcamp release URLs.

    Bandcamp artwork is extracted from the release's JSON-LD metadata in the
    page HTML. This implementation follows the approach used in the beetcamp
    project.

    See https://github.com/snejus/beetcamp/blob/main/beetcamp/metaguru.py

    Returns the url the the art.
    """

    # For size formats, see https://stackoverflow.com/a/69481878
    bandcamp_art_format = 4

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"User-Agent": "Beets-Flask/1.0"},
            ) as response:
                if response.status != 200:
                    log.error(
                        f"Error fetching Bandcamp art for {url}: {response.status}"
                    )
                    return None

                html = await response.text()

        match = re.search(r'.*"@id".*', html)
        if not match:
            return None

        data = json.loads(match.group(0).strip())
        meta = data[0] if isinstance(data, list) else data
        target_meta = meta.get("inAlbum") or meta
        image = target_meta.get("image")

        if isinstance(image, list) and len(image) > 0:
            image = image[0]
        if image:
            return re.sub(
                r"(?<=bcbits\.com/img/a)(\d+)_\d+(?=\.jpg(?:[?#]|$))",
                rf"\1_{bandcamp_art_format}",
                str(image),
            )

        return None
    except (
        aiohttp.ClientError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ) as err:
        log.error(f"Error parsing Bandcamp art for {url}: {err}")
        return None


async def get_discogs_art(url: str) -> str | None:
    """Resolve cover art for Discogs release URLs using the beets token.

    See https://github.com/beetbox/beets/blob/master/beetsplug/discogs/__init__.py

    Returns the url the the art.
    """

    match = re.search(r"discogs\.com/(?:[^/]+/)?release/(\d+)", url)
    if not match:
        return None

    try:
        token = get_config().beets_config["discogs"]["user_token"].as_str()
    except ConfigError:
        token = ""

    if not token:
        log.error("Discogs artwork requires discogs.user_token to be configured")
        return None

    release_id = match.group(1)
    headers = {
        "User-Agent": "Beets-Flask/1.0",
        "Authorization": f"Discogs token={token}",
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                f"https://api.discogs.com/releases/{release_id}"
            ) as response:
                if response.status != 200:
                    log.error(
                        f"Error fetching Discogs art for release {release_id}: "
                        f"{response.status}"
                    )
                    return None

                data = await response.json()

        images = data.get("images", [])
        return images[0].get("uri150") if images else None
    except (
        aiohttp.ClientError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ) as err:
        log.error(f"Error parsing Discogs art for release {release_id}: {err}")
        return None


async def _get_beatport_client():
    """Return or safely initialize the client from the beatport4 plugin.

    See https://github.com/Samik081/beets-beatport4

    Returns the url the the art.
    """

    get_config()
    for plugin in find_plugins():
        if plugin.name != "beatport4":
            continue

        client = getattr(plugin, "client", None)
        if client is not None:
            return client

        tokenfile = getattr(plugin, "_tokenfile", None)
        setup = getattr(plugin, "setup", None)
        if not callable(tokenfile) or not callable(setup):
            return None

        token_path = tokenfile()
        if not isinstance(token_path, (str, bytes, os.PathLike)):
            log.error("Beatport token file path is invalid")
            return None

        if not os.path.isfile(token_path):
            log.error("Beatport artwork requires an existing beatport4 token file")
            return None

        try:
            with open(token_path) as token_file:
                token_data = json.load(token_file)
            token_is_valid = float(token_data["expires_at"]) > time.time() + 30
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            token_is_valid = False

        config = getattr(plugin, "config", None)
        if config is None:
            has_credentials = False
        else:
            try:
                has_credentials = bool(
                    config["username"].get() and config["password"].get()
                )
            except (AttributeError, ConfigError, KeyError, TypeError):
                has_credentials = False

        if not token_is_valid and not has_credentials:
            log.error(
                "Beatport artwork requires a valid token or configured credentials"
            )
            return None

        setup_args = () if len(inspect.signature(setup).parameters) == 0 else (None,)
        await asyncio.to_thread(setup, *setup_args)
        return getattr(plugin, "client", None)

    return None


def _parse_beatport_art_url(url: str):
    """Parse and validate a beatport track/album URL."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None

    host = (parsed.hostname or "").lower()
    if host not in {"beatport.com", "www.beatport.com"}:
        return None

    parsed_match = re.compile(
        r"^/(?P<resource>release|track)/[^/]+/(?P<resource_id>\d+)/?$"
    ).fullmatch(parsed.path)
    if not parsed_match:
        return None

    return parsed_match.group("resource"), parsed_match.group("resource_id")


async def get_beatport_art(url: str) -> str | None:
    """Resolve cover art for Beatport release and track URLs.

    See https://github.com/Samik081/beets-beatport4/blob/main/beetsplug/beatport4/client.py

    Returns the url the the art.
    """

    parsed_beatport_url = _parse_beatport_art_url(url)
    if parsed_beatport_url is None:
        return None

    resource_type, beatport_id = parsed_beatport_url

    try:
        client = await _get_beatport_client()
        if client is None:
            log.error("Beatport artwork requires the beatport4 plugin to be enabled")
            return None
        if resource_type == "release":
            release = await asyncio.to_thread(client.get_release, beatport_id)
            track = release.tracks[0] if release and release.tracks else None
        else:
            track = await asyncio.to_thread(client.get_track, beatport_id)

        if track is None:
            return None
        if track.image_dynamic_url:
            return track.image_dynamic_url.format(w=250, h=250)
        return track.image_url
    except Exception as err:
        log.error(f"Error fetching Beatport art for {url}: {err}")
        return None


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
    return redirect(
        url_for(
            "backend.library.artwork.file_art",
            filepath=quote_plus(path + "/" + files[0]),
        ),
        code=302,
    )
