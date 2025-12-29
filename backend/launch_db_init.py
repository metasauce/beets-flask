import os

# dirty workaround, we pretend this is a rq worker so we get the logger to create
# a child log with pid
os.environ.setdefault("RQ_JOB_ID", "dbin")

from beets.ui import _open_library

from beets_flask.config.beets_config import get_config
from beets_flask.database import setup_database
from beets_flask.logger import log

if __name__ == "__main__":
    log.debug("Launching database init worker")

    # ensue beets own db is created
    config = get_config()
    _open_library(config.beets_config)

    # ensure beets-flask db is created
    setup_database()
