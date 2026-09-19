from time import sleep

from rq.job import Job

import beets_flask.redis


# global `from` import do not work in tests with mock
# from beets_flask.redis import import_queue, preview_queue
def f():
    sleep(0.2)


class TestRedisMock:
    def test_enqueue_global_import(self):
        """Tests that enqueue works as expected in the
        test setup.

        I.e. should run instantly and not be queued.
        """

        assert beets_flask.redis.import_queue.is_async is False
        assert beets_flask.redis.preview_queue.is_async is False

        job = beets_flask.redis.import_queue.enqueue(f)
        assert isinstance(job, Job)
        assert job.result is None
        assert job.is_finished is True

        job = beets_flask.redis.preview_queue.enqueue(f)
        assert isinstance(job, Job)
        assert job.result is None
        assert job.is_finished is True

    def test_enqueue_local_import(self):
        """Tests that enqueue works as expected in the
        test setup.

        I.e. should run instantly and not be queued.
        """
        from beets_flask.redis import import_queue, preview_queue

        assert import_queue.is_async is False
        assert preview_queue.is_async is False

        job = import_queue.enqueue(f)
        assert isinstance(job, Job)
        assert job.result is None
        assert job.is_finished is True

        job = preview_queue.enqueue(f)
        assert isinstance(job, Job)
        assert job.result is None
        assert job.is_finished is True


async def test_wait_for_job_results():
    """Test the wait_for_job_results function.

    Does not make too much sense as jobs are executed synchronously in tests
    but should still work.
    """
    from beets_flask.redis import import_queue, wait_for_job_results

    job = import_queue.enqueue(f)
    result = await wait_for_job_results(job, poll_interval=0.1, timeout=1)
    assert result is None
    assert job.result is None
    assert job.is_finished is True


class TestStore:
    """Tests for the generic TTL object store."""

    def test_store_and_consume_roundtrip(self, fake_redis):
        object_id = beets_flask.redis.store({"foo": "bar"})

        assert object_id
        assert beets_flask.redis.consume(object_id) == {"foo": "bar"}

    def test_consume_is_single_use(self, fake_redis):
        object_id = beets_flask.redis.store("value")

        assert beets_flask.redis.consume(object_id) == "value"
        assert beets_flask.redis.consume(object_id) is None

    def test_consume_unknown_returns_none(self, fake_redis):
        assert beets_flask.redis.consume("does-not-exist") is None

    def test_default_ttl(self, fake_redis):
        object_id = beets_flask.redis.store("value")
        key = f"{beets_flask.redis._KEY_PREFIX}{object_id}"

        # Matches the default of ``store(..., ttl=600)``.
        ttl = fake_redis.ttl(key)
        assert 0 < ttl <= 600

    def test_custom_ttl(self, fake_redis):
        object_id = beets_flask.redis.store("value", ttl=60)
        key = f"{beets_flask.redis._KEY_PREFIX}{object_id}"

        ttl = fake_redis.ttl(key)
        assert 0 < ttl <= 60
