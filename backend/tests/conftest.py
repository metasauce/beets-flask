import hashlib
import logging
import os
import pickle
import shutil
from collections.abc import Callable, Generator
from contextlib import _GeneratorContextManager
from pathlib import Path

import pytest
import yaml
from beets import autotag
from beets.autotag import tag_album as _tag_album
from quart import Quart
from quart.typing import TestClientProtocol
from sqlalchemy.orm import Session

from beets_flask.importer.types import BeetsLibrary
from beets_flask.server.app import create_app

log = logging.getLogger(__name__)


@pytest.fixture(autouse=True, scope="session")
def setup_and_teardown(tmpdir_factory):
    """General setup and teardown for the tests

    This creates a temporary directory for the beets library and
    the beets-flask configuration.
    Also sets all environment variables needed for the tests.
    """

    # Setup beets to use the tempdir
    # for reference, see also
    # https://github.com/beetbox/beets/blob/22163d70a77449d83670e60ad3758474463de31b/beets/test/helper.py#L196
    tmp_dir = tmpdir_factory.mktemp("beets_flask")
    os.environ["HOME"] = str(tmp_dir)
    os.environ["BEETSDIR"] = str(tmp_dir / "beets")
    os.makedirs(name=tmp_dir / "beets", exist_ok=True)
    os.environ["BEETSFLASKDIR"] = str(tmp_dir / "beets-flask")
    os.makedirs(name=tmp_dir / "beets-flask", exist_ok=True)
    os.environ["IB_SERVER_CONFIG"] = "test"

    # ---------------------- Overwrite default settings ---------------------- #

    # Let's not create default configs that wouldnt pass our tests
    with open(tmp_dir / "beets-flask/config.yaml", "w") as f:
        yaml.dump({"gui": {"num_preview_workers": 4}}, f)

    # we have one test that does replacements on this file
    # and assumes the default 4 workers
    with open(tmp_dir / "beets/config.yaml", "w") as f:
        yaml.dump({"plugins": ["musicbrainz", "spotify"]}, f)

    yield

    # Teardown
    shutil.rmtree(tmp_dir)


@pytest.fixture(name="testapp", scope="session")
def fixture_testapp():
    app = create_app("test")

    yield app


@pytest.fixture(name="client")
def fixture_client(testapp: Quart) -> TestClientProtocol:
    # Needs beets_lib to be initialized for environment variables
    return testapp.test_client()


@pytest.fixture(name="runner")
def fixture_runner(app):
    return app.test_cli_runner()


# ----------------------------- Database fixtures ---------------------------- #
# Both for our and the beets database


@pytest.fixture(name="db_session_factory")
def db_session_factory(
    testapp,
) -> Callable[..., _GeneratorContextManager[Session, None, None]]:
    from beets_flask.database import db_session_factory

    return db_session_factory


@pytest.fixture(name="db_session")
def db_session(db_session_factory):
    with db_session_factory() as session:
        yield session


@pytest.fixture(scope="function")
def beets_lib() -> Generator[BeetsLibrary, None, None]:
    import beets.library

    lib = beets.library.Library(path=os.environ["BEETSDIR"] + "/library.db")

    # Copy test audio data
    source = Path(__file__).parent / "data" / "audio"
    dest = Path(os.environ["HOME"]) / "audio"
    Path(dest).mkdir(exist_ok=True)

    shutil.copytree(source, dest, dirs_exist_ok=True)

    yield lib

    os.remove(os.environ["BEETSDIR"] + "/library.db")

    # Clean up the copied files
    shutil.rmtree(dest)


def beets_lib_item(**kwargs):
    """
    Usage:

    beets_lib.add(item(title="the title", artist="the artist", album="the album"))
    """
    import beets.library

    default_kwargs = dict(
        title="the title",
        artist="the artist",
        albumartist="the album artist",
        album="the album",
        genre="the genre",
        lyricist="the lyricist",
        composer="the composer",
        arranger="the arranger",
        grouping="the grouping",
        year=1,
        month=2,
        day=3,
        track=4,
        tracktotal=5,
        disc=6,
        disctotal=7,
        lyrics="the lyrics",
        comments="the comments",
        path=os.environ["HOME"] + "/audio/test.mp3",
    )
    default_kwargs.update(kwargs)

    i = beets.library.Item(
        None,
        **default_kwargs,
    )
    return i


def beets_lib_album(**kwargs):
    """
    Usage:

    beets_lib.add(album(title="the title", artist="the artist"))
    """
    import beets.library

    default_kwargs = dict(
        album="the album",
        albumartist="the album artist",
        genre="the genre",
        year=1,
        month=2,
        day=3,
        tracktotal=5,
        disctotal=7,
        lyrics="the lyrics",
        comments="the comments",
        artpath=os.environ["HOME"] + "/audio/cover.png",
    )
    default_kwargs.update(kwargs)

    a = beets.library.Album(
        db=None,
        **default_kwargs,
    )
    return a


# ---------------------------------- Mocking --------------------------------- #


@pytest.fixture(autouse=True)
def local_redis(monkeypatch):
    """Mock all redis calls with rq
    see https://python-rq.org/docs/testing/
    see https://docs.pytest.org/en/7.1.x/how-to/monkeypatch.html#global-patch-example-preventing-requests-from-remote-operations
    """

    from fakeredis import FakeStrictRedis
    from rq import Queue

    log.debug("Mocking beets_flask.redis")
    monkeypatch.setattr(
        "beets_flask.redis.import_queue",
        Queue("import", is_async=False, connection=FakeStrictRedis()),
    )
    monkeypatch.setattr(
        "beets_flask.redis.preview_queue",
        Queue("preview", is_async=False, connection=FakeStrictRedis()),
    )
    yield
    log.debug("Unmocking beets_flask.redis")
    monkeypatch.undo()


@pytest.fixture(scope="session", autouse=True)
def mock_tag_album():
    """Fixture that monkeypatches beets tag_album to use cached lookups.

    Caches MusicBrainz lookups in ``/tmp/beets_lookup_cache_<version>/`` so
    they survive across test runs but are keyed by beets version.

    We must patch both ``beets.autotag.tag_album`` (the public API) and
    ``beets.importer.tasks.tag_album`` (where the actual call site lives,
    imported directly from ``beets.autotag.match``, bypassing the public API).
    """
    import beets
    import beets.importer.tasks as tasks_mod

    # Persistent cache in /tmp, keyed by beets version
    cache_dir = Path(f"/tmp/beets_lookup_cache_{beets.__version__}")
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Save originals from both patched locations.
    # beeets.importer.tasks imports tag_album directly from
    # beets.autotag.match (not via beets.autotag), so we must
    # patch that module's attribute too.  Use setattr to avoid
    # pyright reportPrivateImportUsage on the re-imported name.
    _original_autotag = autotag.tag_album
    _original_tasks = getattr(tasks_mod, "tag_album")

    def _cached_tag_album(
        items,
        search_artist: str | None = None,
        search_name: str | None = None,
        search_ids: list[str] = [],
    ):
        # Compute stable hash from items and search parameters
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

        cache_file = cache_dir / f"lookup_{items_hash}.pickle"
        if cache_file.exists():
            log.debug(f"Using cached lookup from {cache_file}")
            with open(cache_file, "rb") as f:
                return pickle.load(f)

        # Real lookup on cache miss
        res = _tag_album(items, search_artist, search_name, search_ids)
        with open(cache_file, "wb") as f:
            pickle.dump(res, f)
        return res

    # Patch both locations so the wrapper intercepts all call paths
    autotag.tag_album = _cached_tag_album
    setattr(tasks_mod, "tag_album", _cached_tag_album)

    yield cache_dir

    # Restore originals
    autotag.tag_album = _original_autotag
    setattr(tasks_mod, "tag_album", _original_tasks)
