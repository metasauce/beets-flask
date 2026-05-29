import asyncio
import logging

from beets_flask.importer.pipeline import AsyncPipeline


async def test_smoke_async(caplog):
    """Async version of the beets smoke test
    for pipeline
    """

    # no idea what happens with the test
    # when logging is configured differently
    log = logging.getLogger("logger")
    log.setLevel(logging.INFO)

    async def produce():
        for i in range(5):
            log.info(f"producing {i}")
            await asyncio.sleep(0.05)
            yield i

    async def work():
        num = yield
        while True:
            log.info(f"working {num}")
            num = yield num * 2

    async def consume():
        while True:
            num = yield
            await asyncio.sleep(0.05)
            log.info(f"consuming {num}")

    initial_task = produce()
    stages = [work(), consume()]
    pipeline: AsyncPipeline = AsyncPipeline(initial_task, stages)

    await pipeline.run_async()
    assert caplog.record_tuples == [
        ("logger", logging.INFO, "producing 0"),
        ("logger", logging.INFO, "working 0"),
        ("logger", logging.INFO, "consuming 0"),
        ("logger", logging.INFO, "producing 1"),
        ("logger", logging.INFO, "working 1"),
        ("logger", logging.INFO, "consuming 2"),
        ("logger", logging.INFO, "producing 2"),
        ("logger", logging.INFO, "working 2"),
        ("logger", logging.INFO, "consuming 4"),
        ("logger", logging.INFO, "producing 3"),
        ("logger", logging.INFO, "working 3"),
        ("logger", logging.INFO, "consuming 6"),
        ("logger", logging.INFO, "producing 4"),
        ("logger", logging.INFO, "working 4"),
        ("logger", logging.INFO, "consuming 8"),
    ]
