from __future__ import annotations

from datetime import datetime, timedelta

from quart import jsonify, request
from rq.job import Job
from sqlalchemy import select

from beets_flask import invoker
from beets_flask.database import db_session_factory
from beets_flask.database.mapper.base import Context
from beets_flask.database.mapper.states import SessionStateMapper
from beets_flask.database.models.states import (
    FolderInDb,
    SessionStateInDb,
    TaskStateInDb,
)
from beets_flask.importer.progress import FolderStatus, Progress
from beets_flask.logger import log
from beets_flask.server.exceptions import (
    InvalidUsageException,
    NotFoundException,
    SerializedException,
)
from beets_flask.server.utility import (
    pop_extra_meta,
    pop_folder_params,
    pop_query_param,
)
from beets_flask.server.websocket.status import FolderStatusUpdate, JobStatusUpdate

from .base import ModelAPIBlueprint

__all__ = ["SessionAPIBlueprint"]


class SessionAPIBlueprint(ModelAPIBlueprint[SessionStateInDb]):
    def __init__(self):
        super().__init__(SessionStateInDb, url_prefix="/session")

    def _register_routes(self) -> None:
        """Register the routes for the blueprint."""
        super()._register_routes()
        self.blueprint.route("/by_folder", methods=["POST"])(self.get_by_folder)
        self.blueprint.route("/status", methods=["GET"])(self.get_status)
        self.blueprint.route("/enqueue", methods=["POST"])(self.enqueue)
        self.blueprint.route("/add_candidates", methods=["POST"])(self.add_candidates)

    async def get_by_folder(self):
        """Returns the most recent session state for a given folder hash or path."""

        params = await request.get_json()
        folder_hashes, folder_paths = pop_folder_params(params, allow_mismatch=True)

        if len(folder_hashes) != 1 and len(folder_paths) != 1:
            raise InvalidUsageException(
                "Provide one folder hash OR one folder path", status_code=400
            )

        with db_session_factory() as db_session:
            item = self.model.get_by_hash_and_path(
                hash=folder_hashes[0],
                path=folder_paths[0],
                db_session=db_session,
            )

            if not item:
                # TODO: by path, validation of session hash
                # raise, but we do not want to spam the
                # frontend console with errors.
                # we manually handle this in sessionQueryOptions.
                raise NotFoundException(
                    f"Item with {folder_hashes=} {folder_paths=} not found",
                    status_code=200,
                )

            mapper = SessionStateMapper(want_to_serialize=True)
            live_state = mapper.from_db(item, Context())
            return jsonify(live_state.serialize())

    async def enqueue(self):
        """Start a new session for a given folder hash or enqueue a new job for an existing session.

        You need to specify the folder of the album,
        and it has to be a valid album folder.

        # Params
        - `kind` (str): The kind of the tag. See `invoker.EnqueueKind`.

        """
        params = await request.get_json()
        folder_hashes, folder_paths = pop_folder_params(params)
        kind = pop_query_param(params, "kind", str)
        if not isinstance(kind, str):
            raise InvalidUsageException(
                "kind must be one of " + str(invoker.EnqueueKind.__members__)
            )

        extra_meta = pop_extra_meta(params, n_jobs=len(folder_hashes))

        jobs: list[Job] = []

        for hash, path, meta in zip(folder_hashes, folder_paths, extra_meta):
            jobs.append(
                await invoker.enqueue(
                    hash,
                    str(path),
                    invoker.EnqueueKind.from_str(kind),
                    extra_meta=meta,
                    **params,
                )
            )

        return jsonify(
            JobStatusUpdate(
                message=f"{len(jobs)} added as kind: {kind}",
                num_jobs=len(jobs),
                job_metas=[j.get_meta() for j in jobs],  # type: ignore
            )
        )

    async def add_candidates(self):
        """Search for new candidates.

        Helper function which is pretty similar to enqueue. But only allows for a single
        folder hash and path.
        """
        params = await request.get_json()
        task_id = pop_query_param(params, "task_id", str)
        session_id = pop_query_param(params, "session_id", str)

        folder_hash: str | None = None
        folder_path: str | None = None
        with db_session_factory() as db_session:
            # Get path, hash by task_id
            if session_id is not None:
                stmt_session = select(SessionStateInDb).where(
                    SessionStateInDb.id == session_id
                )
                session_indb = db_session.execute(stmt_session).scalar_one_or_none()
                if session_indb is None:
                    raise InvalidUsageException(
                        f"Session with session_id {session_id} not found",
                    )

                folder_path = session_indb.folder.full_path
                folder_hash = session_indb.folder.hash

            if task_id is not None:
                stmt_task = select(TaskStateInDb).where(TaskStateInDb.id == task_id)
                task_indb = db_session.execute(stmt_task).scalar_one_or_none()
                if task_indb is None:
                    raise InvalidUsageException(
                        f"Task with task_id {task_id} not found",
                    )

                folder_path = task_indb.session.folder.full_path
                folder_hash = task_indb.session.folder.hash

        if folder_hash is None or folder_path is None:
            raise InvalidUsageException(
                "task_id or session_id must be provided",
            )

        extra_meta = pop_extra_meta(params, n_jobs=1)

        job = await invoker.enqueue(
            folder_hash,
            folder_path,
            invoker.EnqueueKind.PREVIEW_ADD_CANDIDATES,
            extra_meta=extra_meta[0],
            **params,
        )

        return jsonify(
            JobStatusUpdate(
                message=f"searching_candidates for {folder_path} folders",
                num_jobs=1,
                job_metas=[job.get_meta()],  # type: ignore
            )
        )

    async def get_status(self):
        """Get all pending tasks."""

        params = await request.get_json()
        folder_hashes, folder_paths = pop_folder_params(params)

        stats: list[FolderStatusUpdate] = []

        if len(folder_hashes) == 0:
            stmt = select(FolderInDb).order_by(FolderInDb.created_at.desc())
            with db_session_factory() as session:
                folders = session.execute(stmt).scalars().all()
                folder_hashes = [f.hash for f in folders]
                folder_paths = [f.full_path for f in folders]

        log.debug(f"Checking status for {len(folder_hashes)} folders")

        for hash, path in zip(folder_hashes, folder_paths):
            log.debug(f"Checking folder status via session from db: {path} ({hash})")
            db_status, db_date, db_exc = _get_folder_status_from_db(hash)
            log.debug(f"Found {db_status=} {db_date=} {db_exc=}")

            log.debug(f"Checking folder status via job queues: {path} ({hash})")
            job_status, job_date, job_exc = _get_folder_status_from_queues(hash)
            log.debug(f"Found {job_status=} {job_date=} {job_exc=}")

            # just for None casting, timezones prevent comparing
            if db_date is not None:
                db_date = db_date.replace(tzinfo=None)
            if job_date is not None:
                job_date = job_date.replace(tzinfo=None)

            status = FolderStatus.UNKNOWN
            exc = None
            if db_date is None and job_date is None:
                pass
            elif (db_date or datetime.min) + timedelta(seconds=1) >= (
                job_date or datetime.min
            ):
                # Sometimes, the job_date might be some .7secs after db_date and would
                # get favoured, so we added a second of leeway.
                log.debug(f"Using status from DB: {db_date} >= {job_date}")
                status = db_status
                exc = db_exc
            else:
                log.debug(f"Using status from job queue : {db_date} < {job_date}")
                status = job_status
                exc = job_exc

            stats.append(
                FolderStatusUpdate(path=str(path), hash=hash, status=status, exc=exc)
            )

        return jsonify(stats)


def _get_folder_status_from_db(
    hash: str,
) -> tuple[FolderStatus, datetime | None, SerializedException | None]:
    with db_session_factory() as db_session:
        stmt_s = (
            select(SessionStateInDb)
            .where(SessionStateInDb.folder_hash == hash)
            .order_by(SessionStateInDb.folder_revision.desc())
        )
        s_state_indb = db_session.execute(stmt_s).scalars().first()
        if s_state_indb is None:
            return FolderStatus.UNKNOWN, None, None
        else:
            # PS: This progress <-> state mapping feels inconsistent.
            # There should be a better place for this.
            status = FolderStatus.UNKNOWN
            if s_state_indb.progress == Progress.NOT_STARTED:
                status = FolderStatus.NOT_STARTED
            elif s_state_indb.progress == Progress.DELETING:
                status = FolderStatus.DELETING
            elif s_state_indb.progress == Progress.DELETION_COMPLETED:
                status = FolderStatus.DELETED
            elif s_state_indb.progress == Progress.PREVIEW_COMPLETED:
                status = FolderStatus.PREVIEWED
            elif s_state_indb.progress == Progress.IMPORT_COMPLETED:
                status = FolderStatus.IMPORTED
            elif s_state_indb.progress < Progress.PREVIEW_COMPLETED:
                status = FolderStatus.PREVIEWING
            elif s_state_indb.progress < Progress.IMPORT_COMPLETED:
                status = FolderStatus.IMPORTING

            if s_state_indb.exception is not None:
                exc = s_state_indb.exception
                status = FolderStatus.FAILED
            else:
                exc = None

            return status, s_state_indb.updated_at, exc


def _get_folder_status_from_queues(
    hash: str,
) -> tuple[FolderStatus, datetime | None, SerializedException | None]:
    from beets_flask.redis import queues, redis_conn

    # could not simply import queues from beets_flask.redis ?
    # queues = [import_queue, preview_queue]

    # hold a list of jobs, sorted by the queue/job status
    q_kinds: dict[str, list[Job]] = {
        "queued": [],
        "scheduled": [],
        "started": [],
        "failed": [],
        "finished": [],
    }

    for q in queues:
        q_kinds["queued"].extend(_get_jobs(q, connection=redis_conn))
        q_kinds["scheduled"].extend(
            _get_jobs(q.scheduled_job_registry, connection=redis_conn)
        )
        q_kinds["started"].extend(
            _get_jobs(q.started_job_registry, connection=redis_conn)
        )
        q_kinds["failed"].extend(
            _get_jobs(q.failed_job_registry, connection=redis_conn)
        )
        q_kinds["finished"].extend(
            _get_jobs(q.finished_job_registry, connection=redis_conn)
        )

    # We always want the latest info, no matter from which queue.
    job_date = None
    status = FolderStatus.UNKNOWN
    exc = None

    for kind in q_kinds.keys():
        jobs = q_kinds[kind]

        meta_job_date = _is_hash_in_jobs(hash, jobs)
        if meta_job_date is None:
            # Hash not found
            continue

        meta, job, _job_date = meta_job_date
        if job_date is None or _job_date > job_date:
            job_date = _job_date
        else:
            # Job is not newer than from other queue
            continue

        if kind in ["queued", "scheduled"]:
            status = FolderStatus.PENDING
        elif kind == "failed":
            status = FolderStatus.FAILED
        elif kind == "started":
            if "import" in meta["job_kind"]:
                status = FolderStatus.IMPORTING
            elif "preview" in meta["job_kind"]:
                status = FolderStatus.PREVIEWING
            else:
                raise ValueError("Unknown job kind")
        elif kind == "finished":
            if "import" in meta["job_kind"]:
                status = FolderStatus.IMPORTED
            elif "preview" in meta["job_kind"]:
                status = FolderStatus.PREVIEWED
            else:
                raise ValueError("Unknown job kind")
        else:
            status = FolderStatus.UNKNOWN

        # Additional check the return value of the job for
        # exception values

        # log.debug(
        #     f"Job details:\n"
        #     + f"{job.enqueued_at=}\n"
        #     + f"{job.started_at=}\n"
        #     + f"{job.created_at=}\n"
        #     + f"{job.ended_at=}\n"
        #     + f"{job.enqueue_at_front=}"
        # )

        # We normally catch failed jobs early on but just
        # in case we also check
        res = job.latest_result()
        if (
            res is not None
            and res.return_value is not None
            # HACK: SerializedException contains a type and message attribute
            and isinstance(res.return_value, dict)
            and "type" in res.return_value
            and "message" in res.return_value
        ):
            exc = SerializedException(
                type=res.return_value["type"],
                message=res.return_value["message"],
                description=res.return_value.get("description"),
                trace=res.return_value.get("trace"),
            )
            status = FolderStatus.FAILED
        else:
            exc = None

    return status, job_date, exc


def _get_jobs(registry, connection):
    jobs = Job.fetch_many(registry.get_job_ids(), connection=connection)
    jobs = [j for j in jobs if j is not None]

    return jobs


def _is_hash_in_jobs(
    hash: str, jobs: list[Job]
) -> tuple[dict[str, str], Job, datetime] | None:
    for j in jobs:
        meta = j.get_meta(False)
        if meta.get("folder_hash") == hash:
            # jobs dont have an updated_at attribute.
            job_dates = [
                d
                for d in [
                    j.enqueued_at,  # at least this one should never be None.
                    j.started_at,
                    j.created_at,
                    j.ended_at,
                ]
                if d is not None
            ]

            return meta, j, max(job_dates)
    return None
