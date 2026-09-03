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
        not "assets" in path
        and not "logo_beets.png" in path
        and not "logo_flask.png" in path
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


@frontend_bp.route("/api_docs")
async def redoc():
    return """
    <redoc spec-url="./openapi.json"></redoc>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"> </script>
    """
