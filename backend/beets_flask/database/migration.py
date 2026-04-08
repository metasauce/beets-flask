from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from beets_flask.config.flask_config import get_flask_config
from beets_flask.logger import log


def run_migrations() -> None:
    """Run all pending database migrations."""

    alembic_config = Config("alembic.ini")
    engine = create_engine(get_flask_config()["DATABASE_URI"])

    if not _db_has_tables(engine):
        # Completely empty database - run full migrations to create tables
        log.info("Database empty, running initial migration...")
        command.upgrade(alembic_config, "head")
    elif not _alembic_initialized(engine):
        # Has tables but no alembic tracking - stamp then upgrade
        log.info("Database has no alembic tracking yet")
        stamp_initial(alembic_config)
        command.upgrade(alembic_config, "head")
    else:
        # Already tracked - just run pending migrations
        log.info("Running database migrations...")
        command.upgrade(alembic_config, "head")

    log.info("Database migrations complete.")


def stamp_initial(config: Config) -> str | None:
    """Stamp the database with the base migration.

    Use this for existing databases that should be considered up-to-date
    at the base migration, without running any schema changes.
    """
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(config)
    base_rev = script.get_base()

    if base_rev is None:
        log.warning("No migrations found, skipping stamp")
        return None

    log.info(f"Stamping database with base migration: {base_rev}...")
    command.stamp(config, base_rev)
    log.info(f"Database stamped with {base_rev}.")
    return base_rev


def _alembic_initialized(engine: Engine) -> bool:
    """Check if alembic_version table exists and has content."""
    with engine.connect() as c:
        result = c.execute(text("PRAGMA table_info(alembic_version)"))
        if not result.fetchall():
            return False  # Table doesn't exis

        # Check if has content
        result = c.execute(text("SELECT EXISTS(SELECT 1 FROM alembic_version)"))
        return bool(result.scalar())


def _db_has_tables(engine: Engine) -> bool:
    """Check if any tables exist in the database."""
    with engine.connect() as c:
        result = c.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        )
        count = result.scalar() or 0
        return count > 0
