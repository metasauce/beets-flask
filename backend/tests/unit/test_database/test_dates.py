import datetime
from pathlib import Path

from beets_flask.database.models import SessionStateInDb
from beets_flask.importer.session import SessionState
from tests.mixins.database import IsolatedDBMixin


class TestDates(IsolatedDBMixin):
    """Test that dates are set correctly in the database for SessionStateInDb objects.

    This test checks that the created_at and updated_at fields are set to the current
    time in UTC when a SessionStateInDb object is created, and that they are
    deserialized correctly from the database.
    """

    def test_dates(self, db_session_factory, tmpdir_factory):
        # Create a new session state in db
        state = SessionState(Path(tmpdir_factory.mktemp("dates_test")))

        state_in_db = SessionStateInDb.from_live_state(state)
        with db_session_factory() as s:
            s.add(state_in_db)
            s.commit()

        # Check that the dates are set
        with db_session_factory() as s:
            state_in_db = s.query(SessionStateInDb).filter_by(id=state_in_db.id).one()
            assert state_in_db.created_at is not None
            assert state_in_db.updated_at is not None

            # Check that the dates are deserialized correctly
            assert isinstance(state_in_db.created_at, datetime.datetime)
            assert isinstance(state_in_db.updated_at, datetime.datetime)

            # Check that the timezone is UTC
            assert state_in_db.created_at.tzinfo is not None
            assert state_in_db.updated_at.tzinfo is not None
            assert state_in_db.created_at.tzinfo == datetime.UTC
            assert state_in_db.updated_at.tzinfo == datetime.UTC

            # Should be approximately equal to current local time
            now = datetime.datetime.now().astimezone()

            assert abs((state_in_db.created_at.astimezone() - now).total_seconds()) < 5
            assert abs((state_in_db.updated_at.astimezone() - now).total_seconds()) < 5
