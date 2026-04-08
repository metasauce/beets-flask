"""Tests for database migration module."""

from unittest.mock import Mock

from sqlalchemy import text

from beets_flask.database.migration import (
    _alembic_initialized,
    _db_has_tables,
    run_migrations,
)


class TestDbHasTables:
    """Tests for _db_has_tables function."""

    def test_returns_false_for_empty_database(self, db_session):
        """Test that _db_has_tables returns False for an empty database."""
        # Drop all
        from beets_flask.database.models.base import Base

        Base.metadata.drop_all(db_session.bind)
        db_session.execute(text("DROP TABLE IF EXISTS test_table"))
        db_session.commit()

        assert _db_has_tables(db_session.bind) is False

    def test_returns_true_when_tables_exist(self, db_session):
        """Test that _db_has_tables returns True when tables exist."""
        db_session.execute(text("CREATE TABLE test_table (id INTEGER)"))
        db_session.commit()

        assert _db_has_tables(db_session.bind) is True


class TestAlembicInitialized:
    """Tests for _alembic_initialized function."""

    def test_returns_false_when_table_does_not_exist(self, db_session):
        """Test that _alembic_initialized returns False when table doesn't exist."""
        assert _alembic_initialized(db_session.bind) is False

    def test_returns_true_when_table_has_content(self, db_session):
        """Test that _alembic_initialized returns True when table has content."""
        db_session.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32))")
        )
        db_session.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('abc123')")
        )
        db_session.commit()

        assert _alembic_initialized(db_session.bind) is True

    def test_returns_false_when_table_exists_but_empty(self, db_session):
        """Test that _alembic_initialized returns False when table exists but is empty."""
        db_session.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32))")
        )
        db_session.execute(text("DELETE FROM alembic_version"))
        db_session.commit()

        assert _alembic_initialized(db_session.bind) is False


class TestRunMigrations:
    """Tests for run_migrations function."""

    def test_runs_upgrade_empty_db(self, caplog):
        import beets_flask.database.migration as mig

        mig._db_has_tables = Mock(return_value=False)
        mig.command.upgrade = Mock()

        run_migrations()
        mig._db_has_tables.assert_called_once()
        mig.command.upgrade.assert_called_once()

        # Check log
        assert "Database empty" in caplog.text
        assert "Database migrations complete." in caplog.text

    def test_runs_upgrade_alembic_missing(self, caplog):
        import beets_flask.database.migration as mig

        mig._db_has_tables = Mock(return_value=True)
        mig._alembic_initialized = Mock(return_value=False)
        mig.command.upgrade = Mock()

        run_migrations()
        mig._db_has_tables.assert_called_once()
        mig.command.upgrade.assert_called_once()
        mig._alembic_initialized.assert_called_once()

        # Check log
        assert "Database has no alembic" in caplog.text
        assert "Database migrations complete." in caplog.text

    def test_runs_upgrade_alembic_exist(self, caplog):
        import beets_flask.database.migration as mig

        mig._db_has_tables = Mock(return_value=True)
        mig._alembic_initialized = Mock(return_value=True)
        mig.command.upgrade = Mock()

        run_migrations()
        mig._db_has_tables.assert_called_once()
        mig.command.upgrade.assert_called_once()
        mig._alembic_initialized.assert_called_once()

        # Check log
        assert "Running database migrations..." in caplog.text
        assert "Database migrations complete." in caplog.text
