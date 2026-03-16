from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    ParamSpec,
    TypeVar,
)

from beets.ui import _open_library
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from beets_flask.config import get_config
from beets_flask.database import db_session_factory
from beets_flask.database.models.states import (
    FolderInDb,
    SessionState,
    SessionStateInDb,
)
from beets_flask.importer.progress import FolderStatus
from beets_flask.importer.session import (
    AddCandidatesSession,
    AutoImportSession,
    BootlegImportSession,
    CandidateChoice,
    ImportSession,
    PreviewSession,
    Search,
    TaskIdMappingArg,
    UndoSession,
    delete_from_beets,
)
from beets_flask.importer.types import DuplicateAction
from beets_flask.logger import log
from beets_flask.redis import import_queue, preview_queue
from beets_flask.server.exceptions import (
    InvalidUsageException,
    exception_as_return_value,
)
from beets_flask.server.websocket.status import (
    JobStatusUpdate,
    emit_folder_status,
    send_status_update,
)

from .job import ExtraJobMeta, _set_job_meta

if TYPE_CHECKING:
    from rq.job import Job
    from rq.queue import Queue


def emit_update_on_job_change(job, connection, result, *args, **kwargs):
    """
    Callback for rq enqueue functions to emit a job status update via websocket.

    See https://python-rq.org/docs/#success-callback
    """
    log.debug(f"job update for socket {job=} {connection=} {result=} {args=} {kwargs=}")

    def _is_serialized_exception(d: Any):
        # I wish we could to instance checks on our SerializedException TypedDict
        if not isinstance(result, dict):
            return False
        if "type" in d and "message" in d.keys():
            # the other keys are optional
            return True
        return False

    try:
        asyncio.run(
            send_status_update(
                JobStatusUpdate(
                    message="Job status update",
                    num_jobs=1,
                    job_metas=[job.get_meta()],
                    exc=result if _is_serialized_exception(result) else None,
                )
            )
        )
    except Exception as e:
        log.error(f"Failed to emit job update: {e}", exc_info=True)


P = ParamSpec("P")  # Parameters
R = TypeVar("R")  # Return


def _enqueue(
    queue: Queue,
    f: Callable[P, Any | Awaitable[Any]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> Job:
    """Enqueue a job in redis.

    Helper that sets some shared behavior and allows
    to for proper type hinting.
    """

    job = queue.enqueue(
        f,
        *args,
        **kwargs,
        on_success=emit_update_on_job_change,
    )
    return job


class EnqueueKind(Enum):
    """Enum for the different kinds of sessions we can enqueue."""

    PREVIEW = "preview"
    PREVIEW_ADD_CANDIDATES = "preview_add_candidates"
    IMPORT_CANDIDATE = "import_candidate"
    IMPORT_AUTO = "import_auto"
    IMPORT_UNDO = "import_undo"
    IMPORT_BOOTLEG = "import_bootleg"
    # Bootlegs are essentially asis, but does not mean to just import the asis candidate,
    # it has its own session that also groups albums, and skips previews.

    _AUTO_IMPORT = "_auto_import"
    _AUTO_PREVIEW = "_auto_preview"

    @classmethod
    def from_str(cls, kind: str) -> EnqueueKind:
        """Convert a string to an EnqueueKind enum.

        Parameters
        ----------
        kind : str
            The string to convert.
        """
        try:
            return cls[kind.upper()]
        except KeyError:
            raise ValueError(f"Unknown kind {kind}")


@emit_folder_status(before=FolderStatus.PENDING)
async def enqueue(
    hash: str,
    path: str,
    kind: EnqueueKind,
    extra_meta: ExtraJobMeta | None = None,
    **kwargs,
) -> Job:
    """Delegate a preview or import to a redis worker, depending on its kind.

    Parameters
    ----------
    hash : str
        The hash of the folder to enqueue.
    path : str
        The path of the folder to enqueue.
    kind : EnqueueKind
        The kind of the folder to enqueue.
    extra_meta: ExtraJobMeta, optional
        Extra meta data to pass to the job. E.g. use this to assign a reference
        for the frontend to the job, so we can track it via the websocket.
    kwargs : dict
        Additional arguments to pass to the worker functions. Depend on the kind,
        use with care.
    """
    if extra_meta is None:
        extra_meta = ExtraJobMeta()

    match kind:
        case EnqueueKind.PREVIEW:
            job = enqueue_preview(hash, path, extra_meta, **kwargs)
        case EnqueueKind.PREVIEW_ADD_CANDIDATES:
            job = enqueue_preview_add_candidates(hash, path, extra_meta, **kwargs)
        case EnqueueKind.IMPORT_AUTO:
            job = enqueue_import_auto(hash, path, extra_meta, **kwargs)
        case EnqueueKind.IMPORT_CANDIDATE:
            job = enqueue_import_candidate(hash, path, extra_meta, **kwargs)
        case EnqueueKind.IMPORT_BOOTLEG:
            job = enqueue_import_bootleg(hash, path, extra_meta, **kwargs)
        case EnqueueKind.IMPORT_UNDO:
            job = enqueue_import_undo(hash, path, extra_meta, **kwargs)
        case _:
            raise InvalidUsageException(f"Unknown kind {kind}")

    log.debug(f"Enqueued {job.id=} {job.meta=}")

    return job


# --------------------------- Enqueue entry points --------------------------- #
# Mainly input validation and submitting to the redis queue


def enqueue_preview(hash: str, path: str, extra_meta: ExtraJobMeta, **kwargs) -> Job:
    group_albums: bool | None = kwargs.pop("group_albums", None)
    autotag: bool | None = kwargs.pop("autotag", None)

    if len(kwargs.keys()) > 0:
        raise InvalidUsageException("EnqueueKind.PREVIEW does not accept any kwargs.")
    job = _enqueue(preview_queue, run_preview, hash, path, group_albums, autotag)
    _set_job_meta(job, hash, path, EnqueueKind.PREVIEW, extra_meta)
    return job


def enqueue_preview_add_candidates(
    hash: str, path: str, extra_meta: ExtraJobMeta, **kwargs
) -> Job:
    # May contain search_ids, search_artist, search_album
    # As always to allow task mapping

    search: TaskIdMappingArg[Search | Literal["skip"]] = kwargs.pop("search", None)
    if len(kwargs.keys()) > 0:
        raise InvalidUsageException(
            "EnqueueKind.PREVIEW_ADD_CANDIDATES only accepts the following kwargs: "
            + "search"
        )

    if search is None:
        raise InvalidUsageException(
            "EnqueueKind.PREVIEW_ADD_CANDIDATES requires a search kwarg."
        )

    # kwargs are mixed between our own function and redis enqueue -.-
    # if we accidentally define a redis kwarg for our function, it will be ignored.
    # https://python-rq.org/docs/#enqueueing-jobs
    job = _enqueue(
        preview_queue,
        run_preview_add_candidates,
        hash,
        path,
        search=search,
    )
    _set_job_meta(job, hash, path, EnqueueKind.PREVIEW_ADD_CANDIDATES, extra_meta)
    return job


def enqueue_import_candidate(
    hash: str, path: str, extra_meta: ExtraJobMeta, **kwargs
) -> Job:
    """
    Imports a candidate that has been fetched in a preview session.

    Kwargs
    ------
    candidate_id : CandidateChoice | dict[str, CandidateChoice] | None
        A valid candidate id for a candidate that has been fetched in a preview
        session.
        None stands for best, is resolved in the session.
        additionally, if a dict is provided, it maps from task_id to candidate, and dupicate action, respectively.
    duplicate_actions
        See candidate_id.
    TODO: Also allowed: "asis" (no exact match needed, there is only one
        asis-candidate).
    """

    candidate_ids: TaskIdMappingArg[CandidateChoice] = kwargs.pop("candidate_ids", None)
    duplicate_actions: TaskIdMappingArg[DuplicateAction] = kwargs.pop(
        "duplicate_actions", None
    )

    if len(kwargs.keys()) > 0:
        raise InvalidUsageException(
            "EnqueueKind.IMPORT only accepts the following kwargs: "
            + "candidate_ids, duplicate_actions."
        )

    # TODO: Validation: lookup candidates exits

    # For convenience: if the user calls this but no preview was generated before,
    # use the auto-import instead (which also fetches previews).
    try:
        # TODO: along with validation:
        # we need a special flag as task_id that stands for "do this for all tasks"
        # used along with candidate_ids length == 1.
        # then, only run the fallback auto-import for the args coming from gui import button

        # If the user did not specify a candidate_id, we assume they want the best
        # candidate.
        with db_session_factory() as db_session:
            _get_live_state_by_folder(hash, path, db_session)
            # raises if no state found
    except:
        log.info(
            f"No previous session state fround for {hash=} {path=} "
            + "switching to auto-import"
        )
        return enqueue_import_auto(hash, path, extra_meta)

    job = _enqueue(
        import_queue,
        run_import_candidate,
        hash,
        path,
        candidate_ids=candidate_ids,
        duplicate_actions=duplicate_actions,
    )
    _set_job_meta(job, hash, path, EnqueueKind.IMPORT_CANDIDATE, extra_meta)
    return job


def enqueue_import_auto(hash: str, path: str, extra_meta: ExtraJobMeta, **kwargs):
    """
    Enqueue an automatic import.

    Auto jobs first generate a preview (if needed) and then run an import, which always
    imports the best candidate - but only if the preview is good enough (as specified
    in the users beets config)

    This is a two step process, and previews run in another queue (thread) than imports.

    See AutoImportSession for more details.
    """

    group_albums: bool | None = kwargs.pop("group_albums", None)
    autotag: bool | None = kwargs.pop("autotag", None)
    import_threshold: float | None = kwargs.pop("import_threshold", None)
    duplicate_actions: TaskIdMappingArg[DuplicateAction] = kwargs.pop(
        "duplicate_actions", None
    )

    if len(kwargs.keys()) > 0:
        raise InvalidUsageException(
            "EnqueueKind.IMPORT_AUTO only accepts the following kwargs: "
            + "group_albums, autotag, import_threshold, duplicate_actions."
        )

    # We only assign the on_success callback (likely coming
    # via a kwarg) to the second job!
    job1 = preview_queue.enqueue(
        run_preview, hash, path, group_albums=group_albums, autotag=autotag, **kwargs
    )
    _set_job_meta(job1, hash, path, EnqueueKind._AUTO_PREVIEW, extra_meta)
    job2 = _enqueue(
        import_queue,
        run_import_auto,
        hash,
        path,
        import_threshold=import_threshold,
        duplicate_actions=duplicate_actions,
        **kwargs,
        # rq has no proper typing therefore our kwargs are not type checked properly
        depends_on=job1,  # type: ignore
    )
    _set_job_meta(job2, hash, path, EnqueueKind._AUTO_IMPORT, extra_meta)

    return job2


def enqueue_import_bootleg(hash: str, path: str, extra_meta: ExtraJobMeta, **kwargs):
    job = _enqueue(import_queue, run_import_bootleg, hash, path, **kwargs)
    _set_job_meta(job, hash, path, EnqueueKind.IMPORT_BOOTLEG, extra_meta)
    return job


def enqueue_import_undo(hash: str, path: str, extra_meta: ExtraJobMeta, **kwargs):
    delete_files: bool = kwargs.pop("delete_files", True)

    if len(kwargs.keys()) > 0:
        raise InvalidUsageException(
            "EnqueueKind.IMPORT_UNDO only accepts the following kwargs: "
            + "delete_files."
        )

    job = _enqueue(
        import_queue,
        run_import_undo,
        hash,
        path,
        delete_files=delete_files,
    )
    _set_job_meta(job, hash, path, EnqueueKind.IMPORT_UNDO, extra_meta)
    return job


def enqueue_delete_items(task_ids: list[str]) -> Job:
    """Enqueue to delete items from the beets library.

    A bit of a special case as this does not use the normal
    hash and path based enqueueing.
    """
    job = _enqueue(
        import_queue,
        delete_items,
        task_ids,
        True,
        # rq has no proper typing therefore our kwargs are not type checked properly
        at_front=True,  # type: ignore
    )
    return job


# -------------------- Functions that run in redis workers ------------------- #
# TODO: We might want to move these to their own file, for a bit better separation of
# concerns.


# redis preview queue
@exception_as_return_value
@emit_folder_status(before=FolderStatus.PREVIEWING, after=FolderStatus.PREVIEWED)
async def run_preview(
    hash: str,
    path: str,
    group_albums: bool | None,
    autotag: bool | None,
):
    """Fetch candidates for a folder using beets.

    Will refetch candidates if this is rerun even if candidates exist
    in the db.

    Current convention is we have one session for one folder *has*, but
    We might have multiple sessions for the same folder **path**.
    Previews will **reset** any previous session state in the database, if they
    exist for the same folder hash.

    Parameters
    ----------
    hash : str
        The hash of the folder for which to run the preview.
    path : str
        The path of the folder for which to run the preview.
    group_albums : bool | None
        Whether to create multple tasks, one for each album found in the metadata
        of the files. Set to true if you have multiple albums in a single folder.
        If None: get value from beets config.
    autotag : bool | None
        Whether to look up metadata online. If None: get value from beets config.
    """

    log.info(f"Preview task on {hash=} {path=}")

    with inbox_config_override(path), db_session_factory() as db_session:
        f_on_disk = FolderInDb.get_current_on_disk(hash, path)
        if hash != f_on_disk.hash:
            log.warning(
                f"Folder content has changed since the job was scheduled for {path}. "
                + f"Using new content ({f_on_disk.hash}) instead of {hash}"
            )

        # here, in preview, we always want to start from a fresh state
        # an existing state would skip the candidate lookup.
        # otherwise, the retag action would not work, as preview starting from
        s_state_live = SessionState(f_on_disk)
        p_session = PreviewSession(
            s_state_live, group_albums=group_albums, autotag=autotag
        )

        try:
            await p_session.run_async()
        finally:
            # Get max revision for this folder hash
            stmt = select(func.max(SessionStateInDb.folder_revision)).where(
                SessionStateInDb.folder_hash == hash,
            )
            max_rev = db_session.execute(stmt).scalar_one_or_none()
            new_rev = 0 if max_rev is None else max_rev + 1
            s_state_indb = SessionStateInDb.from_live_state(p_session.state)
            s_state_indb.folder_revision = new_rev

            db_session.merge(s_state_indb)
            db_session.commit()

    log.info(f"Preview done. {hash=} {path=}")


# redis preview queue
@exception_as_return_value
@emit_folder_status(before=FolderStatus.PREVIEWING, after=FolderStatus.PREVIEWED)
async def run_preview_add_candidates(
    hash: str, path: str, search: TaskIdMappingArg[Search | Literal["skip"]]
):
    """Adds a candidate to an session which is already in the status tagged.

    This only works if all session tasks are tagged. I.e. preview completed.

    Parameters
    ----------
    search : dict[str, Search]
        A dictionary of task ids to search dicts. No value or none skips the search
        for this task.
    """
    log.info(f"Add preview candidates task on {hash=}")

    with inbox_config_override(path), db_session_factory() as db_session:
        s_state_live = _get_live_state_by_folder(hash, path, db_session)

        a_session = AddCandidatesSession(
            s_state_live,
            search=search,
        )
        try:
            await a_session.run_async()
        finally:
            s_state_indb = SessionStateInDb.from_live_state(a_session.state)
            db_session.merge(instance=s_state_indb)
            db_session.commit()

    log.info(f"Add candidates done. {hash=} {path=}")


# redis import queue
@exception_as_return_value
@emit_folder_status(before=FolderStatus.IMPORTING, after=FolderStatus.IMPORTED)
async def run_import_candidate(
    hash: str,
    path: str,
    candidate_ids: TaskIdMappingArg[CandidateChoice],
    duplicate_actions: TaskIdMappingArg[DuplicateAction],
):
    """Imports a candidate that has been fetched in a preview session.

    Parameters
    ----------
    candidate_id : optional
        If candidate_id is none the best candidate is used.
    duplicate_action : optional
        If duplicate_action is none, the default action from the config is used.
    """
    log.info(f"Import task on {hash=} {path=}")

    with inbox_config_override(path), db_session_factory() as db_session:
        s_state_live = _get_live_state_by_folder(hash, path, db_session)

        i_session = ImportSession(
            s_state_live,
            candidate_ids=candidate_ids,
            duplicate_actions=duplicate_actions,
        )

        try:
            await i_session.run_async()
        finally:
            s_state_indb = SessionStateInDb.from_live_state(i_session.state)
            db_session.merge(instance=s_state_indb)
            db_session.commit()

    log.info(f"Import candidate done. {hash=} {path=}")


# redis import queue
@exception_as_return_value
@emit_folder_status(before=FolderStatus.IMPORTING, after=FolderStatus.IMPORTED)
async def run_import_auto(
    hash: str,
    path: str,
    import_threshold: float | None,
    duplicate_actions: TaskIdMappingArg[DuplicateAction],
):
    log.info(f"Auto Import task on {hash=} {path=}")

    with inbox_config_override(path), db_session_factory() as db_session:
        s_state_live = _get_live_state_by_folder(hash, path, db_session)
        i_session = AutoImportSession(
            s_state_live,
            import_threshold=import_threshold,
            duplicate_actions=duplicate_actions,
        )

        try:
            await i_session.run_async()
        finally:
            s_state_indb = SessionStateInDb.from_live_state(i_session.state)
            db_session.merge(instance=s_state_indb)
            db_session.commit()

    log.info(f"Auto Import done. {hash=} {path=}")


# redis import queue
@exception_as_return_value
@emit_folder_status(before=FolderStatus.IMPORTING, after=FolderStatus.IMPORTED)
async def run_import_bootleg(hash: str, path: str):
    log.info(f"Bootleg Import task on {hash=} {path=}")

    with inbox_config_override(path), db_session_factory() as db_session:
        # TODO: add duplicate action
        # TODO: sort out how to generate previews for asis candidates
        s_state_live = _get_live_state_by_folder(
            hash, path, create_if_not_exists=True, db_session=db_session
        )
        i_session = BootlegImportSession(s_state_live)

        try:
            await i_session.run_async()
        finally:
            s_state_indb = SessionStateInDb.from_live_state(i_session.state)
            db_session.merge(instance=s_state_indb)
            db_session.commit()

    log.info(f"Bootleg Import done. {hash=} {path=}")


@exception_as_return_value
@emit_folder_status(before=FolderStatus.DELETING, after=FolderStatus.DELETED)
async def run_import_undo(hash: str, path: str, delete_files: bool):
    log.info(f"Import Undo task on {hash=} {path=}")

    with inbox_config_override(path), db_session_factory() as db_session:
        s_state_live = _get_live_state_by_folder(hash, path, db_session)
        i_session = UndoSession(s_state_live, delete_files=delete_files)

        try:
            await i_session.run_async()
        finally:
            s_state_indb = SessionStateInDb.from_live_state(i_session.state)
            db_session.merge(instance=s_state_indb)
            db_session.commit()

    log.info(f"Import Undo done. {hash=} {path=}")


# ---------------------------------- Helper ---------------------------------- #


def _get_live_state_by_folder(
    hash: str, path: str, db_session: Session, create_if_not_exists=False
) -> SessionState:
    f_on_disk = FolderInDb.get_current_on_disk(hash, path)
    if hash != f_on_disk.hash:
        log.warning(
            f"Folder content has changed since the job was scheduled for {path}. "
            + f"Using new content ({f_on_disk.hash}) instead of {hash}"
        )

    s_state_indb = SessionStateInDb.get_by_hash_and_path(
        # we warn about hash change, and want the import to still run
        # but on the old hash.
        hash=hash,
        path=path,
        db_session=db_session,
    )

    if s_state_indb is None and create_if_not_exists:
        s_state_live = SessionState(f_on_disk)
        return s_state_live

    if s_state_indb is None:
        # TODO: rq error handling
        raise InvalidUsageException(
            f"No session state found for {path=} {hash=} "
            + f"fresh_hash_on_disk={f_on_disk}, this should not happen."
        )

    log.debug(f"Using existing session state for {path=}")
    s_state_live = s_state_indb.to_live_state()

    # we need this expunge, otherwise we cannot overwrite session states:
    # If object id is in session we cant add a new object to the session with the
    # same id this will raise (see below session.merge)
    db_session.expunge_all()

    return s_state_live


def delete_items(task_ids: list[str], delete_files: bool = True):
    lib = _open_library(get_config().beets_config)
    for task_id in task_ids:
        delete_from_beets(task_id, delete_files=delete_files, lib=lib)


@contextmanager
def inbox_config_override(path):
    """
    Context manager for applying inbox-specific overrides.

    Ensures that overrides are reset even if inner code raises exceptions.
    """
    from beets_flask.watchdog.inbox import get_inbox_for_path

    config = get_config()
    inbox = get_inbox_for_path(path)
    if inbox is None:
        log.warning(f"{path} is not in an inbox, this should only happen in tests")
    else:
        config.apply_inbox_specific_overrides(inbox.path)

    try:
        yield config
    finally:
        config.reset_inbox_specific_overrides()
