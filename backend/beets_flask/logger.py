import logging
import logging.config
import os

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "standard": {
            # https://docs.python.org/3/library/logging.html#logrecord-attributes
            "format": "[%(levelname)s] %(name)s: %(message)s"
        },
        "debug": {
            "format": "[%(levelname)-5s] %(asctime)s %(name)s %(filename)-8s:%(lineno)d %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "debug",
            "filename": os.environ.get("BEETSFLASKLOG", "./beets-flask.log"),
            "maxBytes": 1048576,  # 1 MB
            "backupCount": 3,
        },
    },
    "loggers": {
        "": {  # root logger
            "handlers": ["console", "file"],
            "level": os.getenv("LOG_LEVEL_OTHERS", logging.WARNING),
            "propagate": True,
        },
        "beets-flask": {
            "handlers": ["console", "file"],
            "level": os.getenv("LOG_LEVEL_BEETSFLASK", logging.INFO),
            "propagate": False,
        },
    },
}

# On testing only log to console
if "PYTEST_VERSION" in os.environ:
    # Configure minimal logging for pytest
    logging.basicConfig(
        format="[%(levelname)-5s] %(asctime)s %(name)s %(filename)-8s:%(lineno)d %(message)s",
    )
    logging.getLogger("beets-flask").setLevel(logging.DEBUG)
else:
    logging.config.dictConfig(LOGGING_CONFIG)

log = logging.getLogger("beets-flask")

rq_name = os.getenv("RQ_JOB_ID", None)
if rq_name:
    log = log.getChild(rq_name[:4])


log.debug("Logging configured!")
