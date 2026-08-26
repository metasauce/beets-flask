"""Unit tests for the art extension interface and its providers."""

import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from mediafile import Image, MediaFile

from beets_flask.extensions.art import ArtResult, ArtSource
from beets_flask.extensions.providers import ART_SOURCES
from beets_flask.extensions.providers.file import FileArtSource
from beets_flask.extensions.providers.musicbrainz import MusicbrainzArtSource
from beets_flask.extensions.providers.spotify import SpotifyArtSource
from beets_flask.server.routes.art_preview import make_session


class TestArtResult:
    def test_from_url(self):
        result = ArtResult.from_url("https://example.com/x.jpg")
        assert result.urls == ["https://example.com/x.jpg"]
        assert result.data is None
        assert result.content_type is None

    def test_from_urls(self):
        urls = ["a", "b"]
        result = ArtResult.from_urls(urls)
        assert result.urls == urls
        assert result.data is None
        assert result.content_type is None

    def test_from_data(self):
        data = b"data"
        content_type = "image/png"
        result = ArtResult.from_data(data=data, content_type=content_type)
        assert result.urls == []
        assert result.data == data
        assert result.content_type == content_type


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # Spotify
        (
            "https://open.spotify.com/album/4zY3KmQkPOCEln8TWT9exA",
            SpotifyArtSource,
        ),
        (
            "http://open.spotify.com/album/4zY3KmQkPOCEln8TWT9exA",
            SpotifyArtSource,
        ),
        (
            "https://open.spotify.com.evil.com/album/x",
            None,
        ),
        (
            "https://evil.com/?x=open.spotify.com/album/4zY3KmQkPOCEln8TWT9exA",
            None,
        ),
        (
            "ftp://open.spotify.com/album/4zY3KmQkPOCEln8TWT9exA",
            None,
        ),
        # Musicbrainz
        (
            "https://musicbrainz.org/release/1cf2ae06-bb5e-4256-af6c-e40d406abba5",
            MusicbrainzArtSource,
        ),
        (
            "https://notmusicbrainz.org/release/1cf2ae06-bb5e-4256-af6c-e40d406abba5",
            None,
        ),
        (
            "https://musicbrainz.org.evil.com/release/1cf2ae06-bb5e-4256-af6c-e40d406abba5",
            None,
        ),
        (
            "https://evil.com/?x=musicbrainz.org/release/1cf2ae06-bb5e-4256-af6c-e40d406abba5",
            None,
        ),
        # Other
        (
            "https://example.com/album/x",
            None,
        ),
        ("https://example.com/release/x", None),
    ],
)
def test_art_source_matches(url: str, expected: type[ArtSource] | None):
    valid_sources = [s for s in ART_SOURCES if s.matches(url)]

    if expected is None:
        assert not valid_sources
    else:
        assert len(valid_sources) == 1
        assert isinstance(valid_sources[0], expected)


class TestSpotifyArtSourceGetArt:
    url = "https://open.spotify.com/album/4zY3KmQkPOCEln8TWT9exA"

    async def get_art(
        self,
        handler: Callable[[web.Request], Awaitable[web.Response]],
    ) -> ArtResult | None:
        """Call ``get_art`` against a loopback server serving ``handler`` at /oembed."""
        app = web.Application()
        app.router.add_get("/oembed", handler)
        async with TestClient(TestServer(app)) as client:
            source = SpotifyArtSource()
            source.oembed_base = f"http://127.0.0.1:{client.server.port}/oembed"  # type: ignore[misc]
            return await source.get_art(self.url, client.session)

    @pytest.mark.asyncio
    async def test_returns_art_from_thumbnail(self):
        thumbnail = (
            "https://image-cdn-ak.spotifycdn.com/image/"
            "ab67616d00001e0220453e7ab1c42d598d8ff24b"
        )

        async def oembed(request: web.Request) -> web.Response:
            return web.json_response({"thumbnail_url": thumbnail})

        result = await self.get_art(oembed)

        assert result == ArtResult.from_url(thumbnail)

    @pytest.mark.asyncio
    async def test_returns_none_without_thumbnail(self):
        async def oembed(request: web.Request) -> web.Response:
            return web.json_response({"foo": "bar"})

        result = await self.get_art(oembed)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        async def oembed(request: web.Request) -> web.Response:
            return web.Response(status=404)

        result = await self.get_art(oembed)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_client_error(self):
        # A non-JSON content type makes `response.json()` raise a ContentTypeError.
        async def oembed(request: web.Request) -> web.Response:
            return web.Response(text="oops")

        result = await self.get_art(oembed)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_json(self):
        async def oembed(request: web.Request) -> web.Response:
            return web.Response(text="not-json", content_type="application/json")

        result = await self.get_art(oembed)

        assert result is None


class TestMusicbrainzArtSourceGetArt:
    release_id = "1cf2ae06-bb5e-4256-af6c-e40d406abba5"
    url = f"https://musicbrainz.org/release/{release_id}"

    @pytest.mark.asyncio
    async def test_returns_coverart_candidates(self):
        async with aiohttp.ClientSession() as session:
            result = await MusicbrainzArtSource().get_art(self.url, session)

        assert result == ArtResult.from_urls(
            [
                f"https://coverartarchive.org/release/{self.release_id}/front-250",
                f"https://coverartarchive.org/release/{self.release_id}/front",
            ]
        )

    @pytest.mark.asyncio
    async def test_returns_none_for_non_release_url(self):
        async with aiohttp.ClientSession() as session:
            result = await MusicbrainzArtSource().get_art(
                "https://musicbrainz.org/artist/1cf2ae06-bb5e-4256-af6c-e40d406abba5",
                session,
            )

        assert result is None


class TestMakeSession:
    @pytest.mark.asyncio
    async def test_sends_default_user_agent(self):
        received: dict[str, str] = {}

        async def handler(request: web.Request) -> web.Response:
            received["user_agent"] = request.headers.get("User-Agent", "")
            return web.Response()

        app = web.Application()
        app.router.add_get("/", handler)
        async with TestClient(TestServer(app)) as client:
            async with make_session() as session:
                await session.get(f"http://127.0.0.1:{client.server.port}/")

        assert received["user_agent"].startswith("beets-flask/")
        assert "github.com/pSpitzner/beets-flask" in received["user_agent"]

    @pytest.mark.asyncio
    async def test_applies_default_timeout(self):
        async with make_session() as session:
            assert session.timeout.total == 10


class TestFileArtSourceGetArt:
    audio_dir = Path(__file__).resolve().parents[2] / "data" / "audio"

    @pytest.mark.asyncio
    async def test_returns_embedded_art(self, tmp_path):
        cover = (self.audio_dir / "cover.png").read_bytes()
        audio = tmp_path / "track.mp3"
        shutil.copy(self.audio_dir / "test.mp3", audio)
        mediafile = MediaFile(str(audio))
        mediafile.images = [Image(data=cover)]
        mediafile.save()

        async with aiohttp.ClientSession() as session:
            result = await FileArtSource().get_art(f"file://{tmp_path}", session)

        assert result == ArtResult.from_data(cover, "image/png")

    @pytest.mark.asyncio
    async def test_returns_none_for_audio_without_embedded_art(self, tmp_path):
        audio = tmp_path / "track.mp3"
        shutil.copy(self.audio_dir / "test.mp3", audio)
        mediafile = MediaFile(str(audio))
        mediafile.images = []
        mediafile.save()

        async with aiohttp.ClientSession() as session:
            result = await FileArtSource().get_art(f"file://{tmp_path}", session)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_folder(self, tmp_path):
        async with aiohttp.ClientSession() as session:
            result = await FileArtSource().get_art(
                f"file://{tmp_path / 'does-not-exist'}", session
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_folder_without_audio(self, tmp_path):
        (tmp_path / "notes.txt").write_text("hello")

        async with aiohttp.ClientSession() as session:
            result = await FileArtSource().get_art(f"file://{tmp_path}", session)

        assert result is None
