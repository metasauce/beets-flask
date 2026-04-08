from collections.abc import Callable
from contextlib import _GeneratorContextManager

from sqlalchemy import select
from sqlalchemy.orm import Session

from beets_flask.database.models.states import FolderInDb
from beets_flask.database.setup import _reset_database


def test_reset(
    db_session_factory: Callable[..., _GeneratorContextManager[Session, None, None]],
):
    """Test if the database is reset correctly after calling _reset_database."""

    # Write something to db
    with db_session_factory() as db_session:
        f = FolderInDb(path="/test", hash="test", is_album=False)
        db_session.add(f)
        db_session.commit()

    # Check if it exists
    with db_session_factory() as db_session:
        query = select(FolderInDb).where(FolderInDb.full_path == "/test")
        assert db_session.execute(query).scalar_one_or_none() is not None

    # Reset the database
    _reset_database()

    # Check if it is empty
    with db_session_factory() as db_session:
        query = select(FolderInDb).where(FolderInDb.full_path == "/test")
        assert db_session.execute(query).scalar_one_or_none() is None
