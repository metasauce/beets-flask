"""The glue between the compiled vite frontend and our backend."""

from quart import Blueprint, current_app, send_from_directory

frontend_bp = Blueprint("frontend", __name__)


# Register frontend folder
# basically a reverse proxy for the frontend
@frontend_bp.route("/", defaults={"path": "index.html"})
@frontend_bp.route("/<path:path>")
async def reverse_proxy(path):
    """Link to vite resources."""
    # not include assets
    if (
        "assets" not in path
        and "logo_beets.png" not in path
        and "logo_flask.png" not in path
        and not path.startswith("favicon.ico")
    ):
        path = "index.html"

    # Remove everything infront of assets
    if "assets" in path:
        path = path[path.index("assets") :]
    if "logo_beets.png" in path:
        path = path[path.index("logo_beets.png") :]
    if "logo_flask.png" in path:
        path = path[path.index("logo_flask.png") :]

    r = await send_from_directory(current_app.config["FRONTEND_DIST_DIR"], path)
    return r
