import uvicorn

from beets_flask.logger import log

if __name__ == "__main__":
    log.info("Starting uvicorn server")
    log.info("Server running on http://0.0.0.0:5001")
    uvicorn.run(
        "beets_flask.server.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=5001,
        workers=4,
        log_config=None,  # Disable default uvicorn logging config
        access_log=False,
    )
