import asyncio
import json
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import redis
from rq import Queue
from rq.job import Job

# Setup redis connection
if os.environ.get("REDIS_URL"):
    redis_conn = redis.from_url(os.environ["REDIS_URL"])
else:
    redis_conn = redis.Redis()

# Init our different queues
preview_queue = Queue("preview", connection=redis_conn, default_timeout=600)
import_queue = Queue("import", connection=redis_conn, default_timeout=600)


queues = [preview_queue, import_queue]


_KEY_PREFIX = "store:"


def store(value: Any, ttl: int = 600) -> str:
    """Store a JSON-serializable value and return an opaque id (with a TTL).

    The value expires after ``ttl`` seconds. The returned id is what the
    caller hands to :func:`consume` to retrieve (and delete) the value.
    """
    object_id = secrets.token_urlsafe(32)
    redis_conn.set(
        f"{_KEY_PREFIX}{object_id}",
        json.dumps(value),
        ex=ttl,
    )
    return object_id


def consume(object_id: str) -> Any | None:
    """Retrieve and delete a stored value by id (single-use).

    Returns the stored value, or None if the id is unknown or has expired.
    """
    key = f"{_KEY_PREFIX}{object_id}"
    raw = redis_conn.get(key)
    if raw is None:
        return None
    redis_conn.delete(key)
    return json.loads(raw)


async def wait_for_job_results(
    job: Job, poll_interval: float = 0.5, timeout: float = 300
):
    """Wait for a job to finish and return the result.

    Parameters
    ----------
    job : rq.job.Job
        The job to wait for.
    poll_interval : float, optional
        The interval to poll the job status, by default 0.5
    timeout : float, optional
        The timeout for the job, by default 300

    Raises
    ------
    Exception
        If the job fails or times out.

    Returns
    -------
    Any
        The result of the job.
    """

    start_time = time.time()

    with ThreadPoolExecutor() as executor:
        while True:
            # Check if the timeout has been exceeded
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                raise Exception(f"Job timed out after {timeout} seconds")

            await asyncio.get_event_loop().run_in_executor(executor, job.refresh)

            if job.is_finished:
                return job.return_value(False)
            if job.is_failed:
                raise Exception(f"Job failed: {job.exc_info}")
            # Wait for the job to finish
            await asyncio.sleep(poll_interval)


__all__ = [
    "queues",
    "import_queue",
    "preview_queue",
    "redis_conn",
    "wait_for_job_results",
    "store",
    "consume",
]
