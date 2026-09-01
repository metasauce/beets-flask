from contextlib import contextmanager

from quart import Quart
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool

from beets_flask.config import get_flask_config
from beets_flask.logger import log

from .models import Base

engine: Engine | None = None
session_factory: scoped_session[Session]


def setup_database(app: Quart | None = None) -> None:
    """Set up the database connection and session factory for the FLask application.

    This function initializes the global `engine` and `session_factory` variables
    using the database URI specified in the application's configuration. It also
    sets up a teardown hook to gracefully close the database session when the
    application context is torn down.

    Args:
        app (Quart): The Quart application instance.

    Returns
    -------
        None
    """
    _setup_factory()
    if get_flask_config()["RESET_DB_ON_START"]:
        log.warning("Resetting database due to RESET_DB=True in config")
        _reset_database()

    if app is not None:
        # Gracefully shutdown the database session, if launched
        # from within a Flask app context.
        @app.teardown_appcontext
        def shutdown_session(exception=None) -> None:
            session_factory.remove()


def _setup_factory():
    global engine
    global session_factory

    engine = create_engine(
        get_flask_config()["DATABASE_URI"],
        # The following arguments help save some RAM by reducing idle connections
        poolclass=QueuePool,
        pool_size=5,  # Max active connections (was unlimited)
        max_overflow=10,  # Queue overflow
        pool_recycle=3600,  # Recycle stale connections
        pool_pre_ping=True,  # Validate before use
    )
    session_factory = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))


@contextmanager
def db_session_factory(session: Session | None = None):
    """Databases session as context.

    Makes sure sessions are closed at the end.
    If an existing session is provided, it will not be closed at the end.
    This allows to wrap multiple `with db_session()` blocks around each other without closing the outer session.

    Example:
    ```
    with db_session() as session:
        tag.foo = "bar"
        session.merge(tag)
        return tag.to_dict()

    existingSession = session_factory()
    with db_session(session) as s:
        tag.foo = "bar"
        s.merge(tag)
        return tag.to_dict()
    ```
    """
    is_outermost = session is None
    if is_outermost:
        try:
            session = session_factory()
        except NameError:
            _setup_factory()
            session = session_factory()

    try:
        # mypy does not resolve our try/catch for None-Type check. ignore type errors.``
        yield session
        session.commit()  # type: ignore
    except:
        session.rollback()  # type: ignore
        raise
    finally:
        if is_outermost:
            session.close()  # type: ignore


def _reset_database():
    Base.metadata.drop_all(bind=engine)  # type: ignore
    Base.metadata.create_all(bind=engine)  # type: ignore
