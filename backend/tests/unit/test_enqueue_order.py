"""Queue position of user-initiated versus automated jobs."""

from __future__ import annotations

import sys
import time

import pytest
from fakeredis import FakeStrictRedis
from rq import Queue

import beets_flask.invoker  # noqa: F401  (registers the submodule below)

# `beets_flask.invoker.enqueue` is shadowed by the function of the same name.
enqueue_module = sys.modules["beets_flask.invoker.enqueue"]

HASH = "some_hash"
PATH = "/inbox/some_album"
BACKLOG = 3


@pytest.fixture
def backlog_queues(monkeypatch):
    """Non-eager queues on fakeredis that already hold a backlog of jobs."""
    conn = FakeStrictRedis()
    preview = Queue("preview", is_async=True, connection=conn)
    imp = Queue("import", is_async=True, connection=conn)
    for q in (preview, imp):
        for _ in range(BACKLOG):
            q.enqueue(time.time)
    monkeypatch.setattr(enqueue_module, "preview_queue", preview)
    monkeypatch.setattr(enqueue_module, "import_queue", imp)
    # import_candidate only checks that a session exists for the folder.
    monkeypatch.setattr(
        enqueue_module, "_get_live_state_by_folder", lambda *args, **kwargs: None
    )
    return preview, imp


def position(queue: Queue, job) -> int:
    return queue.get_job_ids().index(job.id)


class TestUserJobsSkipTheBacklog:
    """Jobs a user starts from the UI must not wait behind automated jobs.

    With thousands of automated previews and imports queued, a manual import
    used to wait for all of them (hours) while the UI reported a timeout.
    """

    def test_import_candidate(self, backlog_queues):
        _, imp = backlog_queues
        job = enqueue_module.enqueue_import_candidate(HASH, PATH, {})
        assert position(imp, job) == 0

    def test_import_bootleg(self, backlog_queues):
        _, imp = backlog_queues
        job = enqueue_module.enqueue_import_bootleg(HASH, PATH, {})
        assert position(imp, job) == 0

    def test_import_undo(self, backlog_queues):
        _, imp = backlog_queues
        job = enqueue_module.enqueue_import_undo(HASH, PATH, {})
        assert position(imp, job) == 0

    def test_preview_add_candidates(self, backlog_queues):
        preview, _ = backlog_queues
        job = enqueue_module.enqueue_preview_add_candidates(
            HASH, PATH, {}, search={"task": "skip"}
        )
        assert position(preview, job) == 0


class TestAutomatedJobsKeepTheirOrder:
    def test_preview(self, backlog_queues):
        preview, _ = backlog_queues
        job = enqueue_module.enqueue_preview(HASH, PATH, {})
        assert position(preview, job) == BACKLOG

    def test_import_auto(self, backlog_queues):
        preview, imp = backlog_queues
        enqueue_module.enqueue_import_auto(HASH, PATH, {})
        # Its preview goes to the back; the import waits (deferred) for it.
        assert preview.count == BACKLOG + 1
        assert imp.count == BACKLOG
