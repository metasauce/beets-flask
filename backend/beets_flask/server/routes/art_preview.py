"""Fetch art via ids.

Allows fetching of art via different ids. Remote release URLs are
resolved through art source extensions (see `beets_flask.extensions`),
and the resulting artwork is served (or proxied) as image bytes.
"""

from __future__ import annotations

import asyncio
from importlib.metadata import version

import aiohttp
from quart import Blueprint, make_response, redirect, request

from beets_flask.extensions.art import ArtResult
from beets_flask.extensions.providers import ART_SOURCES
from beets_flask.logger import log
from beets_flask.server.exceptions import InvalidUsageException, NotFoundException

art_blueprint = Blueprint("art", __name__, url_prefix="/art")


@art_blueprint.route("", methods=["GET"])
async def redirect_external_art():
    """Resolve cover art for external release URLs used in preview mode."""
    url = request.args.get("url")
    if not url:
        raise InvalidUsageException("Missing required 'url' query parameter.")

    async with make_session() as session:
        art = await resolve_art(url, session)

        if art is None:
            raise NotFoundException("No Artwork preview was found for the given URL.")

        return await _serve_art_result(art, session)


async def resolve_art(url: str, session: aiohttp.ClientSession) -> ArtResult | None:
    """Resolve cover art for a given URL using the registered art sources."""
    valid_sources = sorted(
        (source for source in ART_SOURCES if source.matches(url)),
        key=lambda source: source.priority,
        reverse=True,  # highest priority first
    )

    if not valid_sources:
        log.info("No art sources matched for %s", url)
        return None

    results = await asyncio.gather(
        *(source.get_art(url, session) for source in valid_sources),
        return_exceptions=True,
    )

    for source, result in zip(valid_sources, results):
        if isinstance(result, BaseException):
            log.info(
                "Art source %s failed for %s",
                source.name,
                url,
                exc_info=result,
            )
            continue

        if result is not None:
            return result

    return None


async def fetch_image(
    session: aiohttp.ClientSession, urls: list[str]
) -> tuple[bytes, str] | None:
    """Download and return the first fetchable image from `urls`.

    Returns a (data, content_type) tuple, or None if none of the URLs
    yields an image.
    """
    for candidate in urls:
        if not candidate.startswith(("http://", "https://")):
            continue
        try:
            async with session.get(candidate) as response:
                if response.status != 200:
                    continue
                content_type = response.headers.get("Content-Type", "image/jpeg")
                if not content_type.startswith("image/"):
                    continue
                return await response.read(), content_type
        except aiohttp.ClientError as err:
            log.error(f"Error proxying image {candidate}: {err}")
    return None


async def _image_response(data: bytes, content_type: str | None = None):
    response = await make_response(data)
    response.headers["Content-Type"] = content_type or "image/jpeg"
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


async def _serve_art_result(result: ArtResult, session: aiohttp.ClientSession):
    """Serve an ArtResult as image bytes, proxying remote URLs if needed."""
    if result.data:
        return await _image_response(result.data, result.content_type)

    for target in result.urls:
        if not target.startswith(("http://", "https://")):
            return redirect(target, code=302)

    image = await fetch_image(session, result.urls)
    if image is None:
        raise NotFoundException("No Artwork preview was found for the given URL.")

    data, content_type = image
    return await _image_response(data, content_type)


def make_session() -> aiohttp.ClientSession:
    """Create an :class:`aiohttp.ClientSession` with the backend defaults."""
    return aiohttp.ClientSession(
        headers={
            "User-Agent": f"beets-flask/{version('beets-flask')} (+https://github.com/pSpitzner/beets-flask)"
        },
        timeout=aiohttp.ClientTimeout(total=10),
    )
