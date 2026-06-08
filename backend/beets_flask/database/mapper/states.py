import pickle
from functools import cached_property

from beets_flask.database.models.pending import TaskItem
from beets_flask.database.models.states import (
    CandidateStateInDb,
    FolderInDb,
    SessionStateInDb,
    TaskStateInDb,
)
from beets_flask.importer.states import CandidateState, SessionState, TaskState
from beets_flask.importer.types import BeetsAlbumMatch, BeetsImportTask
from beets_flask.logger import log

from .base import Context, DBMapper
from .match import ItemMapper, MatchMapper


class SessionStateMapper(DBMapper[SessionState, SessionStateInDb]):
    def __init__(self, want_to_serialize=False) -> None:
        """In the case of want_to_serialize we do not load a folder children."""
        self.task_mapper = TaskStateMapper()
        self.want_to_serialize = want_to_serialize

    def _from_db(self, model: SessionStateInDb, ctx: Context) -> SessionState:
        if self.want_to_serialize:
            s_state = SessionState(model.folder.to_live_folder())
        else:
            s_state = SessionState(model.folder.path)

        if s_state.folder_hash != model.folder.hash:
            log.warning(
                f"Folder hash mismatch for {model.folder.path}. "
                f"Expected {model.folder.hash} but got {s_state.folder_hash}."
            )
        s_state.id = model.id
        s_state.created_at = model.created_at
        s_state.updated_at = model.updated_at
        s_state._task_states = [
            self.task_mapper.from_db(task, ctx) for task in model.tasks
        ]
        s_state.exc = pickle.loads(model.exc) if model.exc else None
        return s_state

    def _to_db(self, obj: SessionState, ctx: Context) -> SessionStateInDb:
        return SessionStateInDb(
            id=obj.id,
            folder=FolderInDb(obj.folder_path, obj.folder_hash),
            tasks=[self.task_mapper.to_db(ts, ctx) for ts in obj.task_states],
            progress=obj.progress.progress,
            exc=obj.exc,
        )


class TaskStateMapper(DBMapper[TaskState, TaskStateInDb]):
    def __init__(self) -> None:
        self.item_mapper = ItemMapper()
        self.candidate_mapper = CandidateStateMapper()

    def _from_db(self, model: TaskStateInDb, ctx: Context) -> TaskState:
        """Recreate the live TaskState with underlying task from its stored version in the db."""

        # We just assume it is a normal import task
        beets_task = BeetsImportTask(
            toppath=model.toppath,
            paths=pickle.loads(model.paths),
            items=[
                self.item_mapper.from_db(task_item.item, ctx)
                for task_item in model.pending_items
            ],
        )
        beets_task.choice_flag = model.choice_flag
        beets_task.cur_artist = model.cur_artist
        beets_task.cur_album = model.cur_album
        old_paths: list[bytes] | None = (
            pickle.loads(model.old_paths) if model.old_paths else None
        )
        # TODO: Update type hints once beets is updated
        beets_task.old_paths = old_paths  # type: ignore

        obj = TaskState(beets_task)
        # Slightly hacky: we add the task to the cache early to allow
        # the candidate mapper to find the reference before a return here
        ctx.from_cache[id(model)] = obj

        obj.id = model.id
        obj.created_at = model.created_at
        obj.updated_at = model.updated_at
        obj.candidate_states = [
            self.candidate_mapper.from_db(c, ctx) for c in model.candidates
        ]
        obj.chosen_candidate_state_id = model.chosen_candidate_id
        obj.progress.progress = model.progress

        # Set candidate of beets_task
        obj.task.candidates = [c.match for c in obj.candidate_states]
        return obj

    def _to_db(self, obj: TaskState, ctx: Context) -> TaskStateInDb:
        # Ensure task.items and all candidate mapping keys share identity.
        # Beets mutates only match.items (via imported_items()) during import,
        # and DB roundtrips produce divergent Item objects. Collapse all
        # references here so to_db creates a single Item DB row per logical item.
        for idx, task_item in enumerate(obj.task.items):
            for cs in obj.candidate_states:
                if not isinstance(cs.match, BeetsAlbumMatch):
                    continue
                for match_item in cs.match.mapping.keys():
                    if (
                        match_item.track == task_item.track
                        and match_item.title == task_item.title
                    ):
                        obj.task.items[idx] = match_item
                        break
                else:
                    continue
                break

        # Also replace mapping dict keys in ALL candidates so every
        # candidate shares the same Item objects as task.items.
        for cs in obj.candidate_states:
            if not isinstance(cs.match, BeetsAlbumMatch):
                continue
            new_map = {}
            for mi, track in cs.match.mapping.items():
                for ti in obj.task.items:
                    if mi.track == ti.track and mi.title == ti.title:
                        new_map[ti] = track
                        break
                else:
                    new_map[mi] = track
            cs.match.mapping = new_map

        if hasattr(obj.task, "old_paths"):
            old_paths = obj.task.old_paths
        else:
            old_paths = None

        model = TaskStateInDb(
            id=obj.id,
            toppath=str(obj.toppath).encode("utf-8") if obj.toppath else None,
            paths=obj.task.paths,
            pending_items=[
                TaskItem(item=self.item_mapper.to_db(i, ctx)) for i in obj.items
            ],
            candidates=[],
            chosen_candidate_id=obj.chosen_candidate_state_id,
            progress=obj.progress.progress,
            choice_flag=obj.task.choice_flag,
            cur_artist=obj.task.cur_artist,
            cur_album=obj.task.cur_album,
            old_paths=old_paths,
        )
        ctx.to_cache[id(obj)] = model

        model.candidates = [
            self.candidate_mapper.to_db(c, ctx) for c in obj.candidate_states
        ]
        return model


class CandidateStateMapper(DBMapper[CandidateState, CandidateStateInDb]):
    def __init__(self) -> None:
        self.match_mapper = MatchMapper()

    @cached_property
    def task_mapper(self):
        return TaskStateMapper()

    def _from_db(self, model: CandidateStateInDb, ctx: Context) -> CandidateState:
        obj = CandidateState(
            match=self.match_mapper.from_db(model.match, ctx),
            task_state=self.task_mapper.from_db(model.task, ctx),
        )
        obj.id = model.id
        obj.created_at = model.created_at
        obj.updated_at = model.updated_at
        obj.duplicate_ids = (
            # edge case: "".split() gives ['']
            [] if len(model.duplicate_ids) == 0 else model.duplicate_ids.split(";")
        )
        return obj

    def _to_db(self, obj: CandidateState, ctx: Context) -> CandidateStateInDb:
        return CandidateStateInDb(
            id=obj.id,
            match=self.match_mapper.to_db(obj.match, ctx),
            duplicate_ids=obj.duplicate_ids,
            task=self.task_mapper.to_db(obj.task_state, ctx),
        )
