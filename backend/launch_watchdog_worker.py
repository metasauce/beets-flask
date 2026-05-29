import asyncio
import os
import signal

# dirty workaround, we pretend this is a rq worker so we get the logger to create
# a child log with pid
os.environ.setdefault("RQ_JOB_ID", "wdog")

from beets_flask.config import get_config
from beets_flask.logger import log
from beets_flask.watchdog.inbox import register_inboxes


async def main():
    log.debug("Launching inbox watchdog worker")
    debounce_config = get_config().data.gui.inbox.debounce_before_autotag
    watchdog = register_inboxes(debounce=debounce_config)

    # Serve until a termination signal is received.
    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    def _shutdown():
        log.info("Shutting down watchdog worker")
        if watchdog:
            watchdog.stop()
        stop.set_result(True)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    await stop


if __name__ == "__main__":
    asyncio.run(main())
