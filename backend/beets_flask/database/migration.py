"""
Scaffold for initial alembic setup and all future migrations.

Introduced for migration from beets-flask v1.2.1 to v2.0. We use a python wrapper here
instead of the alembic cli, as this way we get configs and env vars in our usual way.
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, text

from beets_flask.config.flask_config import get_flask_config
from beets_flask.logger import log


def run_migrations() -> None:
    """Run all pending database migrations."""

    alembic_config = Config(Path(__file__).parent.parent.parent / "alembic.ini")
    db_url = get_flask_config()["DATABASE_URI"]
    engine = create_engine(db_url)

    if not _db_has_tables(engine):
        # Completely empty database - run full migrations to create tables
        log.info("Database empty, running initial migration...")
        upgrade(alembic_config, db_url, engine)
    elif not _alembic_initialized(engine):
        # Has tables but no alembic tracking - stamp then upgrade
        log.info("Database has no alembic tracking yet")
        stamp_initial(alembic_config)
        upgrade(alembic_config, db_url, engine)
    else:
        # Already tracked - just run pending migrations
        log.info("Running database migrations...")
        upgrade(alembic_config, db_url, engine)

    log.info("Database migrations complete.")


def stamp_initial(config: Config) -> str | None:
    """Stamp the database with the initial migration.

    Use this for existing databases that should be considered up-to-date
    at the initial migration, without running any schema changes.
    """
    base_rev = "a986c03d9ba3"  # a986c03d9ba3 == initial
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


def upgrade(alembic_config: Config, db_url: str, engine: Engine):
    """Light wrapper around the alembic upgrade command.

    Adds backups and runs a cleanup after migrations.
    """
    if not _needs_migration(alembic_config, engine):
        log.info("No pending migrations. Skipping.")
        return  # No backup, no upgrade

    db_path = urlparse(db_url).path
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_path = Path(db_path).with_suffix(f".backup_{ts}.db")
    shutil.copy2(db_path, backup_path)
    log.info(f"SQLite backup created at {backup_path}")

    try:
        command.upgrade(alembic_config, "head")

        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(FULL);")
            conn.exec_driver_sql("ANALYZE;")
            conn.exec_driver_sql("REINDEX;")
            conn.exec_driver_sql("VACUUM;")
            result = conn.exec_driver_sql("PRAGMA integrity_check;").scalar()
            if result != "ok":
                raise RuntimeError(f"Integrity check failed: {result}")
    except Exception:
        log.exception("Migration failed! Please report this!")
        raise


def _needs_migration(config: Config, engine: Engine) -> bool:
    """Check if any migrations are pending."""
    script = ScriptDirectory.from_config(config)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        current_rev = ctx.get_current_revision()
        head_rev = script.get_current_head()
        return current_rev != head_rev
