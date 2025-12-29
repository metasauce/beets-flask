"""Config endpoints for the frontend.

we need some of our settings in the frontend. proposed solution:
fetch settings once from the backend on first page-load.
"""

from quart import Blueprint, jsonify

from beets_flask.config import get_config

config_bp = Blueprint("config", __name__, url_prefix="/config")


@config_bp.route("/all", methods=["GET"])
async def get_all():
    """Get nested dict representing the full (but redacted) beets config."""
    config = get_config()
    return jsonify(_serializable(config.beets_config.flatten(redact=True)))


@config_bp.route("/", methods=["GET"])
async def get_basic():
    """Get the config settings needed for the gui."""
    config = get_config()

    return jsonify(
        {
            **config.to_dict(extra_fields=False),
            # the following ones are not part of the schema
            "beets_metadata_sources": config.beets_metadata_sources,
            "beets_version": config.beets_version,
        }
    )


@config_bp.route("/yaml/beets", methods=["GET"])
async def get_raw_beets():
    """Get the raw config yaml file."""
    config = get_config()
    path = config.get_beets_config_path()
    with open(path) as f:
        content = f.read()
    return jsonify({"path": path, "content": content})


@config_bp.route("/yaml", methods=["GET"])
async def get_raw():
    """Get the raw config yaml file for beets-flask."""
    config = get_config()
    path = config.get_beets_flask_config_path()
    with open(path) as f:
        content = f.read()
    return jsonify({"path": path, "content": content})


@config_bp.route("/refresh", methods=["POST"])
async def refresh():
    """Refresh the config object.

    Mainly for debug purposes as it only refresh the config for
    the main thread.

    ```
    curl -X POST http://localhost:5001/api_v1/config/refresh
    ```
    """
    from beets_flask.config import get_config

    config = get_config()
    config.reload()
    return jsonify({"status": "ok"})


def _serializable(input):
    """
    Convert bytes to str in a nested dictionary.

    Recursion is used to handle nested dictionaries.
    """
    if isinstance(input, bytes):
        return input.decode("utf-8")
    elif isinstance(input, dict):
        return {k: _serializable(v) for k, v in input.items()}
    elif isinstance(input, list):
        return [_serializable(element) for element in input]
    return input
