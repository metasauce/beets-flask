from sqlalchemy import select

from beets_flask.database import db_session_factory
from beets_flask.database.models import FolderInDb, SessionStateInDb, TaskStateInDb
from beets_flask.server.exceptions import NotFoundException

from .base import ModelAPIBlueprint


class FolderAPIBlueprint(ModelAPIBlueprint[FolderInDb]):
    def __init__(self):
        super().__init__(
            model=FolderInDb,
            url_prefix="/dbfolder",
        )

    def _register_routes(self):
        super()._register_routes()
        # Register any additional routes specific to Folder here
        self.blueprint.route("/by_task/<gui_id>", methods=["GET"])(self.get_by_taskid)

    async def get_by_taskid(self, gui_id: str):
        """Get a folder by an import gui id.

        The import gui id is the same as a task id.
        """
        with db_session_factory() as db_session:
            stmt = (
                select(FolderInDb)
                .join(SessionStateInDb, TaskStateInDb.session_id == SessionStateInDb.id)
                .join(TaskStateInDb, FolderInDb.id == SessionStateInDb.folder_hash)
                .where(
                    TaskStateInDb.id == gui_id,
                )
            )
            folder = db_session.execute(stmt).scalars().first()

            if folder is None:
                raise NotFoundException("Folder not found")

            return folder.to_dict()
