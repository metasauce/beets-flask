from __future__ import annotations

import os
from abc import ABC
from functools import cached_property
from typing import TYPE_CHECKING

import pytest

from beets_flask.config import get_config

if TYPE_CHECKING:
    from beets_flask.importer.types import BeetsLibrary


class IsolatedDBMixin(ABC):
    """
    A pytest mixin class to reset the database before and after ALL
    tests in this class are run.

    Usage:
    ```
    class TestMyFeature(IsolatedDBMixin):
        def test_something(self):
            # add to clean db

        def test_something_else(self):
            # db has data from previous test
    ```
    """

    def reset_database(self):
        """
        Reset the database to a clean state.
        This method is called before and after each test in the class.
        """
        from beets_flask.database.setup import _reset_database

        _reset_database()

    @pytest.fixture(autouse=True, scope="class")
    def setup_database(self):
        """
        Automatically reset the database before and after ALL tests in this class.

        Args:
            db_session_factory: Pytest fixture providing a database session.
        """
        self.reset_database()
        yield
        self.reset_database()


class IsolatedBeetsLibraryMixin(ABC):
    """
    A pytest mixin class to reset the beets library before and after ALL
    tests in this class are run.

    Usage:
    ```
    class TestMyFeature(IsolatedBeetsLibraryMixin):
        def test_something(self):
            # add to clean db

        def test_something_else(self):
            # db has data from previous test
    ```
    """

    @pytest.fixture(autouse=True, scope="class")
    def setup_beetslib(
        self,
    ):
        """Automatically reset the beets library before and after ALL tests in this class."""
        import shutil
        from pathlib import Path

        import beets.library

        try:
            os.remove(os.environ["BEETSDIR"] + "/library.db")
        except OSError:
            pass
        lib = beets.library.Library(
            path=os.environ["BEETSDIR"] + "/library.db",
            directory=os.environ["BEETSDIR"] + "/imported",
        )
        config = get_config().reload()
        config.data.directory = os.environ["BEETSDIR"] + "/imported"
        config.commit_to_beets()

        # Copy test audio data so computed properties (has_cover_art, etc.)
        # that read from disk can access the backing files.
        audio_src = Path(__file__).parent.parent / "data" / "audio"
        audio_dest = Path(os.environ["HOME"]) / "audio"
        audio_dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(audio_src, audio_dest, dirs_exist_ok=True)

        # Reset the beets library to a clean state
        yield
        print("Resetting beets library to a clean state...")
        # Reset the beets library to a clean state
        try:
            os.remove(os.environ["BEETSDIR"] + "/library.db")
        except OSError:
            pass

    @cached_property
    def beets_lib(self) -> BeetsLibrary:
        """Return the beets library instance."""
        import beets.library

        lib = beets.library.Library(
            path=os.environ["BEETSDIR"] + "/library.db",
            directory=os.environ["BEETSDIR"] + "/imported",
        )
        config = get_config().reload()
        config.data.directory = os.environ["BEETSDIR"] + "/imported"
        config.commit_to_beets()

        return lib
