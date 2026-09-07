from quart import Blueprint
from rq.job import Job
from rq.worker import Worker

from beets_flask.redis import queues, redis_conn

monitor_bp = Blueprint("monitor", __name__, url_prefix="/monitor")


@monitor_bp.route("/queues", methods=["GET"])
async def get_queue_status():
    """Get the status of the job queues.

    Returns
    -------
        dict: A dictionary containing the status of each job queue.

    """
    # for q in queues:
    #     clean_registries(q)
    #     clean_worker_registry(q)

    ret_dict = {}
    for q in queues:
        ret_dict[q.name] = {
            "name": q.name,
            "queued": q.count,
            "queued_jobs": q.job_ids,
            "scheduled": q.scheduled_job_registry.count,
            "executing": q.started_job_registry.count,
            "finished": q.finished_job_registry.count,
            "failed": q.failed_job_registry.count,
        }

    return {"queues": ret_dict}


@monitor_bp.route("/workers", methods=["GET"])
async def get_worker_status():
    """Get the status of the RQ workers.

    Returns
    -------
        dict: A dictionary containing the status of each worker.

    """
    workers = Worker.all(connection=redis_conn)

    ret_dict = {}
    for w in workers:
        ret_dict[w.name] = {
            "name": w.name,
            "queues": w.queue_names(),
            "state": w.get_state(),
            "executed": w.successful_job_count,
            "failed": w.failed_job_count,
        }

    return {"workers": ret_dict}


@monitor_bp.route("/jobs", methods=["GET"])
async def get_job_status():
    """Get the status of the jobs in the job queues.

    Returns
    -------
        dict: A dictionary containing the status of each job in each job queue.

    """
    # https://python-rq.org/docs/job_registries/
    ret = []
    for q in queues:
        jobs = Job.fetch_many(
            q.started_job_registry.get_job_ids(), connection=redis_conn
        )
        for j in jobs:
            if j is None:
                continue
            ret.append(
                {
                    "q_name": q.name,
                    "job_id": j.id,
                    "meta": j.get_meta(False),
                }
            )

    return ret


@monitor_bp.route("/debugResetDb", methods=["GET"])
async def reset_database():
    """Reset the sql database.

    Returns
    -------
        dict: A dictionary containing the status of the reset operation.

    """
    from beets_flask.database.setup import _reset_database

    _reset_database()

    return {"status": "success"}
