import importlib.util
from pathlib import Path

import pytest
from confuse import NotFoundError
from quart import Quart

MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "beets_flask"
    / "server"
    / "routes"
    / "art_preview.py"
)
SPEC = importlib.util.spec_from_file_location("art_preview_module", MODULE_PATH)
assert SPEC and SPEC.loader
ART_PREVIEW_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART_PREVIEW_MODULE)


class FakeResponse:
    def __init__(
        self,
        body: str,
        status: int = 200,
        json_data=None,
        content_type: str = "image/jpeg",
    ):
        self._body = body
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.content_type = content_type
        self.url = "https://example.com/"
        self._json_data = json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self._body

    async def json(self):
        return self._json_data if self._json_data is not None else {}

    async def read(self):
        return self._body.encode("utf-8")


class FakeSession:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, *args, **kwargs):
        url = args[0] if args else kwargs.get("url", "")
        if "api.discogs.com" in url:
            return FakeResponse(
                "",
                json_data={
                    "images": [
                        {
                            "uri": "https://i.discogs.com/dCbJYqhymK3_icKu4ga-ZLjKKX4HlPUXvxuvAqfXGkE/rs:fit/g:sm/q:90/h:600/w:600/czM6Ly9kaXNjb2dz/LWRhdGFiYXNlLWlt/YWdlcy9SLTIyNzUy/NzA0LTE2NDkwMTIz/NDAtNTg1MS5qcGVn.jpeg",
                            "uri150": "https://i.discogs.com/Xm-jQMTRVgFCHPT6gp6bfaIcle6mySuDtarItXeMYHU/rs:fit/g:sm/q:40/h:150/w:150/czM6Ly9kaXNjb2dz/LWRhdGFiYXNlLWlt/YWdlcy9SLTIyNzUy/NzA0LTE2NDkwMTIz/NDAtNTg1MS5qcGVn.jpeg",
                        }
                    ]
                },
            )

        if "bandcamp" in url:
            return FakeResponse(
                '{"@id": "https://wyattworld.bandcamp.com/album/ketts-cave", "image": ["https://f4.bcbits.com/img/a1802951586_10.jpg"]}'
            )

        if "spotify" in url:
            return FakeResponse(
                "mock-image",
                json_data={
                    "thumbnail_url": "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e0220453e7ab1c42d598d8ff24b"
                },
            )

        return FakeResponse(
            "mock-image",
            json_data={"thumbnail_url": "https://example.com/cover.jpg"},
        )


@pytest.fixture
def app() -> Quart:
    app = Quart(__name__)
    app.register_blueprint(ART_PREVIEW_MODULE.art_blueprint)
    return app


@pytest.fixture
async def client(app: Quart):
    return app.test_client()


class FakeConfigValue:
    def as_str(self):
        return "discogs-token"


class FakeBeetsFlaskConfig:
    def __init__(self, user_token):
        self.beets_config = {"discogs": {"user_token": user_token}}


class FakeBeatportTrack:
    image_url = "https://geo-media.beatport.com/image_size/1400x1400/deb1ee72-5d97-41ea-84b9-7df937a8eadc.jpg"
    image_dynamic_url = (
        "https://geo-media.beatport.com/image_size/{w}x{h}/"
        "deb1ee72-5d97-41ea-84b9-7df937a8eadc.jpg"
    )


class FakeBeatportRelease:
    tracks = [FakeBeatportTrack()]


class FakeBeatportClient:
    def get_release(self, beatport_id):
        assert beatport_id == "4678214"
        return FakeBeatportRelease()

    def get_track(self, beatport_id):
        assert beatport_id == "19349876"
        return FakeBeatportTrack()


async def fake_to_thread(function, *args):
    return function(*args)


async def fake_get_beatport_client():
    return FakeBeatportClient()


@pytest.mark.parametrize(
    ("url", "_expected_location"),
    [
        pytest.param(
            "https://open.spotify.com/album/4zY3KmQkPOCEln8TWT9exA",
            "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e0220453e7ab1c42d598d8ff24b",
            id="spotify",
        ),
        pytest.param(
            "https://musicbrainz.org/release/1cf2ae06-bb5e-4256-af6c-e40d406abba5",
            "https://coverartarchive.org/release/1cf2ae06-bb5e-4256-af6c-e40d406abba5/front-250",
            id="musicbrainz",
        ),
        pytest.param(
            "https://wyattworld.bandcamp.com/album/ketts-cave",
            "https://f4.bcbits.com/img/a1802951586_4.jpg",
            id="bandcamp",
        ),
        pytest.param(
            "https://www.discogs.com/release/22752704-Wyatt-Netherwood",
            "https://i.discogs.com/Xm-jQMTRVgFCHPT6gp6bfaIcle6mySuDtarItXeMYHU/rs:fit/g:sm/q:40/h:150/w:150/czM6Ly9kaXNjb2dz/LWRhdGFiYXNlLWlt/YWdlcy9SLTIyNzUy/NzA0LTE2NDkwMTIz/NDAtNTg1MS5qcGVn.jpeg",
            id="discogs",
        ),
        pytest.param(
            "https://www.beatport.com/release/jw-beat/4678214",
            "https://geo-media.beatport.com/image_size/250x250/deb1ee72-5d97-41ea-84b9-7df937a8eadc.jpg",
            id="beatport",
        ),
    ],
)
@pytest.mark.asyncio
async def test_preview_route_returns_supported_art(
    client, monkeypatch, url, _expected_location
):
    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)
    monkeypatch.setattr(
        ART_PREVIEW_MODULE,
        "get_config",
        lambda: FakeBeetsFlaskConfig(FakeConfigValue()),
    )
    monkeypatch.setattr(
        ART_PREVIEW_MODULE,
        "_get_beatport_client",
        fake_get_beatport_client,
    )
    monkeypatch.setattr(ART_PREVIEW_MODULE.asyncio, "to_thread", fake_to_thread)

    response = await client.get("/art", query_string={"url": url})

    assert response.status_code == 200
    assert response.headers["Content-Type"] != ""
    payload = await response.get_data()
    assert payload


@pytest.mark.asyncio
async def test_preview_route_returns_error_without_url(client):
    response = await client.get("/art")

    assert response.status_code == 400

    data = await response.get_json()
    assert data["message"] == "url query param is required."


@pytest.mark.asyncio
async def test_preview_route_returns_404_for_unsupported_url(client, monkeypatch):
    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)

    response = await client.get(
        "/art",
        query_string={"url": "https://example.com/unsupported"},
    )

    assert response.status_code == 404

    data = await response.get_json()
    assert data["error"] == "No art found."


@pytest.mark.asyncio
async def test_get_bandcamp_art_parses_page_metadata(monkeypatch):
    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)

    art_url = await ART_PREVIEW_MODULE.get_bandcamp_art(
        "https://wyattworld.bandcamp.com/album/ketts-cave"
    )

    assert art_url == "https://f4.bcbits.com/img/a1802951586_4.jpg"


@pytest.mark.asyncio
async def test_get_discogs_art_uses_first_release_image(monkeypatch):
    monkeypatch.setattr("aiohttp.ClientSession", FakeSession)
    monkeypatch.setattr(
        ART_PREVIEW_MODULE,
        "get_config",
        lambda: FakeBeetsFlaskConfig(FakeConfigValue()),
    )

    art_url = await ART_PREVIEW_MODULE.get_discogs_art(
        "https://www.discogs.com/release/22752704-Wyatt-Netherwood"
    )

    assert (
        art_url
        == "https://i.discogs.com/Xm-jQMTRVgFCHPT6gp6bfaIcle6mySuDtarItXeMYHU/rs:fit/g:sm/q:40/h:150/w:150/czM6Ly9kaXNjb2dz/LWRhdGFiYXNlLWlt/YWdlcy9SLTIyNzUy/NzA0LTE2NDkwMTIz/NDAtNTg1MS5qcGVn.jpeg"
    )


@pytest.mark.asyncio
async def test_get_discogs_art_returns_none_without_token(monkeypatch):
    class MissingConfigValue:
        def as_str(self):
            raise NotFoundError("discogs.user_token")

    monkeypatch.setattr(
        ART_PREVIEW_MODULE,
        "get_config",
        lambda: FakeBeetsFlaskConfig(MissingConfigValue()),
    )

    art_url = await ART_PREVIEW_MODULE.get_discogs_art(
        "https://www.discogs.com/release/22752704-Wyatt-Netherwood"
    )

    assert art_url is None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.beatport.com/release/jw-beat/4678214",
        "https://www.beatport.com/track/jw-beat/19349876",
    ],
)
@pytest.mark.asyncio
async def test_get_beatport_art_uses_dynamic_image_url(monkeypatch, url):
    monkeypatch.setattr(
        ART_PREVIEW_MODULE,
        "_get_beatport_client",
        fake_get_beatport_client,
    )
    monkeypatch.setattr(ART_PREVIEW_MODULE.asyncio, "to_thread", fake_to_thread)

    art_url = await ART_PREVIEW_MODULE.get_beatport_art(url)

    assert (
        art_url
        == "https://geo-media.beatport.com/image_size/250x250/deb1ee72-5d97-41ea-84b9-7df937a8eadc.jpg"
    )


@pytest.mark.asyncio
async def test_get_beatport_art_accepts_url_suffixes(monkeypatch):
    monkeypatch.setattr(
        ART_PREVIEW_MODULE,
        "_get_beatport_client",
        fake_get_beatport_client,
    )
    monkeypatch.setattr(ART_PREVIEW_MODULE.asyncio, "to_thread", fake_to_thread)

    art_url = await ART_PREVIEW_MODULE.get_beatport_art(
        "https://www.beatport.com/release/jw-beat/4678214/?utm_source=test"
    )

    assert (
        art_url
        == "https://geo-media.beatport.com/image_size/250x250/deb1ee72-5d97-41ea-84b9-7df937a8eadc.jpg"
    )


@pytest.mark.asyncio
async def test_get_beatport_art_uses_static_image_fallback(monkeypatch):
    class StaticImageTrack:
        image_url = "https://geo-media.beatport.com/image_size/1400x1400/deb1ee72-5d97-41ea-84b9-7df937a8eadc.jpg"
        image_dynamic_url = None

    class StaticImageClient:
        def get_track(self, beatport_id):
            assert beatport_id == "19349876"
            return StaticImageTrack()

    async def get_static_image_client():
        return StaticImageClient()

    monkeypatch.setattr(
        ART_PREVIEW_MODULE,
        "_get_beatport_client",
        get_static_image_client,
    )
    monkeypatch.setattr(ART_PREVIEW_MODULE.asyncio, "to_thread", fake_to_thread)

    art_url = await ART_PREVIEW_MODULE.get_beatport_art(
        "https://www.beatport.com/track/jw-beat/19349876"
    )

    assert (
        art_url
        == "https://geo-media.beatport.com/image_size/1400x1400/deb1ee72-5d97-41ea-84b9-7df937a8eadc.jpg"
    )


@pytest.mark.asyncio
async def test_get_beatport_art_returns_none_for_empty_release(monkeypatch):
    class EmptyReleaseClient:
        def get_release(self, beatport_id):
            assert beatport_id == "4678214"
            return type("EmptyRelease", (), {"tracks": []})()

    async def get_empty_release_client():
        return EmptyReleaseClient()

    monkeypatch.setattr(
        ART_PREVIEW_MODULE,
        "_get_beatport_client",
        get_empty_release_client,
    )
    monkeypatch.setattr(ART_PREVIEW_MODULE.asyncio, "to_thread", fake_to_thread)

    art_url = await ART_PREVIEW_MODULE.get_beatport_art(
        "https://www.beatport.com/release/jw-beat/4678214"
    )

    assert art_url is None


@pytest.mark.asyncio
async def test_get_beatport_art_rejects_other_hosts(monkeypatch):
    art_url = await ART_PREVIEW_MODULE.get_beatport_art(
        "https://notbeatport.com/release/jw-beat/4678214"
    )

    assert art_url is None


@pytest.mark.asyncio
async def test_get_beatport_client_initializes_from_existing_token(
    monkeypatch, tmp_path
):
    tokenfile = tmp_path / "beatport_token.json"
    tokenfile.write_text(
        '{"access_token": "token", "expires_at": 9999999999, '
        '"refresh_token": "refresh"}'
    )

    class FakeBeatportPlugin:
        name = "beatport4"
        client: FakeBeatportClient | None = None

        def _tokenfile(self):
            return str(tokenfile)

        def setup(self, session=None):
            self.client = FakeBeatportClient()

    plugin = FakeBeatportPlugin()
    monkeypatch.setattr(ART_PREVIEW_MODULE, "get_config", lambda: {})
    monkeypatch.setattr(ART_PREVIEW_MODULE, "find_plugins", lambda: [plugin])
    monkeypatch.setattr(ART_PREVIEW_MODULE.asyncio, "to_thread", fake_to_thread)

    client = await ART_PREVIEW_MODULE._get_beatport_client()

    assert isinstance(client, FakeBeatportClient)


@pytest.mark.asyncio
async def test_get_beatport_client_does_not_prompt_for_expired_token(
    monkeypatch, tmp_path
):
    tokenfile = tmp_path / "beatport_token.json"
    tokenfile.write_text(
        '{"access_token": "expired", "expires_at": 1, "refresh_token": "refresh"}'
    )

    class FakeConfigValue:
        def get(self):
            return None

    class FakeBeatportPlugin:
        name = "beatport4"
        client = None
        config = {
            "username": FakeConfigValue(),
            "password": FakeConfigValue(),
        }
        setup_called = False

        def _tokenfile(self):
            return str(tokenfile)

        def setup(self):
            self.setup_called = True

    plugin = FakeBeatportPlugin()
    monkeypatch.setattr(ART_PREVIEW_MODULE, "get_config", lambda: {})
    monkeypatch.setattr(ART_PREVIEW_MODULE, "find_plugins", lambda: [plugin])

    client = await ART_PREVIEW_MODULE._get_beatport_client()

    assert client is None
    assert plugin.setup_called is False
