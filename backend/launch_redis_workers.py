import os

from beets_flask.config.beets_config import get_config
from beets_flask.logger import log

# Mesmo padrao do backend: em producao o rq fala com o redis compartilhado,
# em dev com o redis local do container. O --url e explicito porque nao
# devemos depender do default do rq.
redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

num_preview_workers: int = 1  # Default value
try:
    num_preview_workers = get_config()["gui"]["num_preview_workers"].get(int)  # type: ignore
    log.debug(f"Got num_preview_workers from config: {num_preview_workers}")
except:
    pass

log.info(f"Starting {num_preview_workers} redis workers for preview generation")
for i in range(num_preview_workers):
    os.system(f'rq worker preview --url "{redis_url}" --log-format "Preview worker $i: %(message)s" &')


# imports are relatively fast, because they use previously fetched previews.
# one worker should be enough, and this avoids problems from simultaneous db writes etc.
num_import_workers = 1
log.info(f"Starting {num_import_workers} redis workers for import")
for i in range(num_import_workers):
    os.system(f'rq worker import --url "{redis_url}" --log-format "Import worker $i: %(message)s" &')
