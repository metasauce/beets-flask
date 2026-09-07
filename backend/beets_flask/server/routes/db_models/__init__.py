from __future__ import annotations

from typing import TYPE_CHECKING

from beets_flask.database.models.states import CandidateStateInDb, TaskStateInDb

from .base import ModelAPIBlueprint
from .folder import FolderAPIBlueprint
from .session import SessionAPIBlueprint

if TYPE_CHECKING:
    from quart import Blueprint, Quart


def register_state_models(app: Blueprint | Quart):
    # Session is a special case and implements some more logic
    app.register_blueprint(SessionAPIBlueprint().blueprint)
    app.register_blueprint(FolderAPIBlueprint().blueprint)

    # It is not really used in the frontend but for future
    # reference we might want to use it
    app.register_blueprint(
        ModelAPIBlueprint(
            TaskStateInDb,
            url_prefix="/task",
        ).blueprint
    )
    app.register_blueprint(
        ModelAPIBlueprint(
            CandidateStateInDb,
            url_prefix="/candidate",
        ).blueprint
    )
