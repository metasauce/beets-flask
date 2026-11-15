"""Exceptions and error handling for the Quart application.

This module contains the error handling logic for the Quart application.
It provides a way to handle errors in a consistent way and return them
serialized to the frontend to handle gracefully.
"""

import traceback

from confuse import ConfigError
from quart import Blueprint, jsonify
from werkzeug.exceptions import HTTPException

from beets_flask import log
from beets_flask.server.exceptions import (
    ApiError,
    IntegrityError,
    InvalidUsageError,
    NotFoundError,
    SerializedException,
)

error_bp = Blueprint("error", __name__)


@error_bp.app_errorhandler(NotImplementedError)
async def handle_not_implemented(error):
    return (
        SerializedException(
            type=type(error).__name__,
            message=str(error),
            description="This feature is not implemented yet",
        ),
        501,
    )


@error_bp.app_errorhandler(ApiError)
async def handle_api_exception(exc: ApiError):
    """Api exceptions can set their own status code.

    see ../exception.py for more details.
    """
    return (
        SerializedException(
            type=type(exc).__name__,
            message=str(exc),
            description=exc.__doc__,
        ),
        exc.status_code,
    )


@error_bp.app_errorhandler(ConfigError)
async def handle_config_exception(error: ConfigError):
    log.error(f"Configuration Error: {error}")
    return (
        SerializedException(
            type=type(error).__name__,
            message=str(error),
            description=error.__doc__,
        ),
        400,
    )


@error_bp.app_errorhandler(FileNotFoundError)
async def handle_file_not_found(error: FileNotFoundError):
    return (
        jsonify(
            SerializedException(
                type=type(error).__name__,
                message=str(error),
                description="This file was not found",
            )
        ),
        404,
    )


@error_bp.app_errorhandler(HTTPException)
async def handle_exception(exc: HTTPException):
    """Return JSON instead of HTML for werkzeug HTTP errors."""
    # start with the correct headers and status code from the error
    return (
        SerializedException(
            type=type(exc).__name__,
            message=str(exc),
            description=exc.description,
        ),
        exc.code or 500,
    )


@error_bp.app_errorhandler(Exception)
async def handle_generic_error(exc: Exception):
    log.exception(f"Unhandled exception: {exc}")
    return (
        SerializedException(
            type=type(exc).__name__,
            message=str(exc),
            description="An unhandled exception occurred",
            trace="".join(traceback.format_tb(exc.__traceback__)),
        ),
        500,
    )


# ---------------------------------------------------------------------------- #
#                      Test the error handling endpoints                       #
# ---------------------------------------------------------------------------- #
# see test/test_routes/test_exceptions.py for more details


# Api exceptions
@error_bp.route("/error/api", methods=["GET"])
async def error():
    raise ApiError("This is a bad request")


@error_bp.route("/error/invalidUsage", methods=["GET"])
async def invalid_usage():
    raise InvalidUsageError("This is a bad request")


@error_bp.route("/error/notFound", methods=["GET"])
async def not_found():
    raise NotFoundError("This is a not found error")


@error_bp.route("/error/integrity", methods=["GET"])
async def integrity():
    raise IntegrityError("This is an integrity error")


# Generic exceptions
@error_bp.route("/error/notImplemented", methods=["GET"])
async def not_implemented():
    raise NotImplementedError("This is not implemented")


@error_bp.route("/error/configError", methods=["GET"])
async def config_error():
    raise ConfigError("This is a config error")


@error_bp.route("/error/fileNotFound", methods=["GET"])
async def file_not_found():
    raise FileNotFoundError("This is a file not found error")


@error_bp.route("/error/genericError", methods=["GET"])
async def generic_error():
    raise Exception("An unhandled exception occurred")
