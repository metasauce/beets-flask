import os
from collections.abc import Callable
from typing import cast

import socketio

from beets_flask.config import get_config
from beets_flask.logger import log

old_on = socketio.AsyncServer.on


# Gets rid of the type error in the decorator
class TypedAsyncServer(socketio.AsyncServer):
    def on(self, event: str, namespace: str | None = None) -> Callable: ...  # type: ignore


if os.environ.get("PYTEST_CURRENT_TEST", ""):
    client_manager = None
else:
    client_manager = socketio.AsyncRedisManager(
        os.environ.get("REDIS_URL", "redis://"),
        redis_options={"socket_timeout": None},
    )

sio: TypedAsyncServer = cast(
    TypedAsyncServer,
    socketio.AsyncServer(
        async_mode="asgi",
        logger=False,
        engineio_logger=False,
        cors_allowed_origins="*",
        client_manager=client_manager,
    ),
)


def register_socketio(app):
    app.asgi_app = socketio.ASGIApp(sio, app.asgi_app, socketio_path="/socket.io")

    # Register all socketio namespaces
    from .status import register_status

    register_status()

    cfg = get_config()
    if not cfg.is_healthy:
        log.warning(
            f"Config loaded with {len(cfg.errors)} error(s), app running on defaults"
        )

    @sio.on("connect")
    async def on_connect(sid, environ):
        """Push config health to every client on connection."""
        current_cfg = get_config()
        await sio.emit(
            "config_status",
            {
                "healthy": current_cfg.is_healthy,
                "errors": [
                    {"message": e.message, "section": str(e.section)}
                    for e in current_cfg.errors
                ],
            },
            to=sid,
        )

    # Terminal setup uses the already-loaded config
    if cfg.data.gui.terminal.enabled:
        log.info("Setting up Web-Terminal")
        from .terminal import register_tmux

        register_tmux()
    else:
        log.info("Web-Terminal is disabled, skipping setup")
