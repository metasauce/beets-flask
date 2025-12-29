"""Handle file uploads."""

import shutil
from asyncio import timeout
from pathlib import Path
from urllib.parse import unquote_plus

import aiofiles
from quart import Blueprint, jsonify, request

from beets_flask.config import get_config
from beets_flask.logger import log
from beets_flask.server.exceptions import InvalidUsageException
from beets_flask.watchdog.inbox import get_inbox_folders

file_upload_bp = Blueprint("file_upload", __name__, url_prefix="/file_upload")


@file_upload_bp.route("/validate", methods=["POST"])
async def validate():
    """Pre-validate headers for upload.

    This is needed as xmlhttprequest does not handle responses gracefully if
    the upload (request body) is not consumed. Tldr: Upload still in progress,
    cant raise exceptions, as returning any response at this point will reset
    the network connection.
    """
    _get_filename_and_dir()

    return jsonify({"status": "ok"}), 200


@file_upload_bp.route("/", methods=["POST"])
async def upload():
    """Handle file upload.

    Intended to be called after /validate (which ensures headers are correct,
    and raises if not).
    If used without the validation step, the upload will still fail, because
    the backend still raises, but we have no way to let the frontend know.
    """
    # validate
    filename, filedir = _get_filename_and_dir()
    log.info(f"Uploading file '{filename}' to '{filedir}' ...")

    temp_path: Path = Path(get_config().data.gui.inbox.temp_dir)
    temp_path.mkdir(parents=True, exist_ok=True)

    # upload to temp location with 1 hour timeout
    async with timeout(60 * 60):
        async with aiofiles.open(temp_path / filename, "wb") as f:
            async for chunk in request.body:
                await f.write(chunk)

    # move to final location
    filedir.mkdir(parents=True, exist_ok=True)
    shutil.move(temp_path / filename, filedir / filename)

    log.info(f"Uploading file {filename} to {filedir} done!")
    return {"status": "ok"}


def _get_filename_and_dir() -> tuple[str, Path]:
    filename = request.headers.get("X-Filename")
    filedir = request.headers.get("X-File-Target-Dir")

    if not filename or not filedir:
        raise InvalidUsageException(
            "Missing header: X-Filename and X-File-Target-Dir are required"
        )

    # Assert filename does not contain path separators
    filename = unquote_plus(filename)
    if "/" in filename or "\\" in filename:
        raise InvalidUsageException(
            "Invalid filename, must not contain path separators."
        )

    filedir = unquote_plus(filedir)
    filedir = Path(filedir).expanduser().resolve()
    is_valid_filepath = False
    for inbox in get_inbox_folders():
        if filedir.is_relative_to(inbox):
            is_valid_filepath = True
            break

    if not is_valid_filepath:
        log.error(f"Invalid target path {filedir}, must be within an inbox.")
        raise InvalidUsageException("Invalid target path, must be within an inbox.")

    return filename, filedir
