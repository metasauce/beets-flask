import os

from beets_flask.config.beets_config import get_config
from beets_flask.logger import log

num_preview_workers: int = 1  # Default value
try:
    num_preview_workers = get_config().data.gui.num_preview_workers
    log.debug(f"Got num_preview_workers from config: {num_preview_workers}")
except:
    pass

log.info(f"Starting {num_preview_workers} redis workers for preview generation")
for i in range(num_preview_workers):
    os.system(f'rq worker preview --log-format "Preview worker $i: %(message)s" &')


# imports are relatively fast, because they use previously fetched previews.
# one worker should be enough, and this avoids problems from simultaneous db writes etc.
num_import_workers = 1
log.info(f"Starting {num_import_workers} redis workers for import")
for i in range(num_import_workers):
    os.system(f'rq worker import --log-format "Import worker $i: %(message)s" &')
