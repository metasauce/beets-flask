"""Auth endpoints for the frontend.

Exposes the registered auth extensions (see `beets_flask.extensions.providers`)
to the frontend: checking which providers are available and running the PKCE
authentication flow.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TypedDict

from quart import Blueprint, jsonify, request

from beets_flask.extensions.auth import AuthExtension, PkceData
from beets_flask.extensions.providers import AUTH_EXTENSIONS
from beets_flask.redis import consume, store
from beets_flask.server.exceptions import InvalidUsageException

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


class AuthProviderStatus(TypedDict):
    name: str
    authenticated: bool


@auth_bp.route("/providers", methods=["GET"])
async def get_providers() -> list[AuthProviderStatus]:
    """List all registered auth providers with their authentication status."""
    providers: list[AuthProviderStatus] = [
        {
            "name": ext.name,
            "authenticated": ext.is_authenticated(),
        }
        for ext in _get_auth_extensions()
    ]
    return providers


class AuthFlow(TypedDict):
    """In-progress PKCE flow handed to the client (see ``AuthExtension``)."""

    url: str
    flow_id: str


@auth_bp.route("/<name>/url", methods=["GET"])
async def get_authentication_url(name: str) -> AuthFlow:
    """Start the PKCE flow for ``name``.

    Returns the URL the user must visit together with an opaque ``flow_id``
    that must be passed back to the ``complete`` endpoint. The sensitive
    flow state stays in the server-side store.
    """
    ext = _get_auth_extension(name)
    try:
        pkce, url = ext.start_authentication()
    except RuntimeError as err:
        raise InvalidUsageException(str(err)) from err
    flow_id = store(asdict(pkce))
    return {"url": url, "flow_id": flow_id}


@auth_bp.route("/<name>/complete", methods=["POST"])
async def complete_authentication(name: str):
    """Complete the PKCE flow for ``name`` using the redirect URL.

    The request body must contain the ``flow_id`` returned by the ``url`` endpoint and the ``redirect_url``.
    """
    ext = _get_auth_extension(name)
    params = await request.get_json()
    redirect_url = params.pop("redirect_url", None)
    flow_id = params.pop("flow_id", None)

    if not redirect_url or not flow_id:
        raise InvalidUsageException(
            "Missing required parameters: 'redirect_url' and 'flow_id' must be provided."
        )

    flow_state = consume(flow_id)
    if flow_state is None:
        raise InvalidUsageException(
            "Auth flow not found or expired. Please start a new flow."
        )

    try:
        pkce = PkceData(**flow_state)
    except TypeError as err:
        raise InvalidUsageException(f"Invalid stored flow data: {err}") from err

    try:
        ext.complete_authentication(pkce, redirect_url)
    except RuntimeError as err:
        raise InvalidUsageException(str(err)) from err
    return jsonify({"authenticated": True})


def _get_auth_extensions() -> list[AuthExtension]:
    """Return the enabled auth extensions from the registry."""
    return [ext for ext in AUTH_EXTENSIONS if ext.is_enabled()]


def _get_auth_extension(name: str) -> AuthExtension:
    """Return the auth extension with the given name, or raise an exception."""
    for ext in _get_auth_extensions():
        if ext.name == name:
            return ext
    raise InvalidUsageException(f"No auth provider found with name '{name}'.")
