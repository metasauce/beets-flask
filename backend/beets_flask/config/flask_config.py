"""Server configuration for flask app.

We have different configurations classes for
different environments further you may create
a custom configuration class for your own needs.

The configuration classes are parse in the `create_app`
function in the `__init__.py` file.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from ..logger import log

cwd = os.getcwd()


class ServerConfig:
    DEBUG = False
    TESTING = False

    # If the database should be reset on start
    # Useful for development
    RESET_DB_ON_START = False

    # If errors should be thrown or
    # caught and logged
    # Enable for production!
    PROPAGATE_EXCEPTIONS = False

    # Database URI
    DATABASE_URI = "sqlite:///beets-flask-sqlite.db"

    # Folder where the frontend build resources are stored
    # FIXME: 2025-06-04 likely we only need this in production.
    FRONTEND_DIST_DIR = "../frontend/dist/"

    # For file uploads
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2 GB

    # Not sure if this is even used!
    SECRET_KEY = "secret"

    def as_dict(self) -> dict:
        return {
            "DEBUG": ServerConfig.DEBUG,
            "TESTING": ServerConfig.TESTING,
            "RESET_DB_ON_START": ServerConfig.RESET_DB_ON_START,
            "PROPAGATE_EXCEPTIONS": ServerConfig.PROPAGATE_EXCEPTIONS,
            "DATABASE_URI": ServerConfig.DATABASE_URI,
            "SECRET_KEY": ServerConfig.SECRET_KEY,
        }

    def __getitem__(self, key):
        return getattr(self, key)


class Testing(ServerConfig):
    TESTING = True
    DATABASE_URI = "sqlite:///:memory:?cache=shared"
    # temporary in-memory database
    # DATABASE_URI = "sqlite://"


class DevelopmentLocal(ServerConfig):
    RESET_DB_ON_START = True
    DEBUG = True
    DATABASE_URI = f"sqlite:///{cwd}/beets-flask-sqlite.db"


class DevelopmentDocker(ServerConfig):
    DATABASE_URI = (
        f"sqlite:////{os.getenv('BEETSFLASKDIR')}/beets-flask-sqlite.db?timeout=5"
    )
    DEBUG = True


# production
class DeploymentDocker(DevelopmentDocker):
    DEBUG = False
    TESTING = False
    PROPAGATE_EXCEPTIONS = True
    FRONTEND_DIST_DIR = "/repo/frontend/dist/"


def init_server_config(input_config: str | ServerConfig | None = None) -> ServerConfig:
    global config

    if isinstance(input_config, ServerConfig):
        config = input_config
    else:
        if input_config is None:
            input_config = os.environ.get("IB_SERVER_CONFIG", "dev_local")
        switch: Mapping[str, type[ServerConfig]] = {
            "dev_local": DevelopmentLocal,
            "dev_docker": DevelopmentDocker,
            "test": Testing,
            "prod": DeploymentDocker,
        }
        if isinstance(input_config, str) and input_config not in switch:
            raise ValueError(f"Invalid config: {config}")
        log.debug(f"Using config: {input_config}")
        # we still have to initalize!
        config = switch[input_config]()

    return config


# if "RQ_WORKER_ID" in os.environ:
# not elegant, but we also need to initalize the config in workers,
# where the app init is not called
# and for some reason it is needed in global space. revisit this in quartz port


config: ServerConfig | None = None


def get_flask_config() -> ServerConfig:
    global config
    if not config:
        config = init_server_config()
    return config
