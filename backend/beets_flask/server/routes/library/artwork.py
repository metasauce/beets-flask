import os
from io import BytesIO
from typing import TYPE_CHECKING, cast

from mediafile import Image, MediaFile  # comes with the beets install
from PIL import Image as PILImage
from quart import (
    Blueprint,
    g,
    jsonify,
    make_response,
    redirect,
    request,
    send_file,
    url_for,
)

from beets_flask.logger import log
from beets_flask.server.exceptions import (
    IntegrityException,
    InvalidUsageException,
    NotFoundException,
)
from beets_flask.server.routes.library.path_utils import resolve_library_path

if TYPE_CHECKING:
    # For type hinting the global g object
    from . import g

__all__ = ["artwork_pb"]

artwork_pb = Blueprint("artwork", __name__)


# Predefined supported sizes
SIZE_PRESETS = {
    "small": (256, 256),
    "medium": (512, 512),
    "large": (1024, 1024),
    "original": None,
}


def parse_size(size_key: str) -> tuple[int, int] | None:
    """Return a size tuple for a given preset key.

    or None for original.
    Raises KeyError if unknown.
    """
    preset = SIZE_PRESETS.get(size_key)
    if preset is None and size_key != "original":
        raise KeyError(f"Unknown size preset '{size_key}'")
    return preset


def parse_art_params() -> tuple[int, tuple[int, int] | None]:
    """Parse common artwork parameters from request."""
    idx = int(request.args.get("index", 0))
    size_key = request.args.get("size", "small")
    try:
        size = parse_size(size_key)
    except KeyError:
        raise InvalidUsageException(
            f"Invalid size key '{size_key}' provided. Supported keys: {', '.join(SIZE_PRESETS.keys())}"
        )
    return idx, size


def get_image_data_from_file(filepath: str, index: int = 0) -> BytesIO:
    """Get image data from a file path."""
    if not os.path.exists(filepath):
        raise IntegrityException(f"File '{filepath}' does not exist.")

    mediafile = MediaFile(filepath)
    images = mediafile.images
    if not images or len(images) <= index:
        raise NotFoundException(
            f"File has no cover art at index {index}: '{filepath}'."
        )

    im: Image = cast(Image, images[index])
    return BytesIO(im.data)


def get_image_count_from_file(filepath: str) -> int:
    """Get number of images from a file path."""
    mediafile = MediaFile(filepath)
    images = mediafile.images
    return len(images) if images else 0


async def send_image(img_data: BytesIO, size: tuple[int, int] | None = None):
    # Resize if preset provided
    if size:
        img_data = _resize(img_data, size)
    response = await make_response(await send_file(img_data, mimetype="image/png"))
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


# -------------------------------- Item Routes ------------------------------- #


@artwork_pb.route("/item/<int:item_id>/nArtworks", methods=["GET"])
async def item_art_idx(item_id: int):
    """Get the number of images for an item."""
    log.debug(f"Item art index query for id:'{item_id}'")

    item = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:'{item_id}' not found in beets db."
        )

    item_path = resolve_library_path(item.path)
    count = get_image_count_from_file(item_path)
    return jsonify({"count": count}), 200


@artwork_pb.route("/item/<int:item_id>/art", methods=["GET"])
async def item_art(item_id: int):
    log.debug(f"Item art query for id:'{item_id}'")

    idx, size = parse_art_params()

    item = g.lib.get_item(item_id)
    if not item:
        raise NotFoundException(
            f"Item with beets_id:'{item_id}' not found in beets db."
        )

    item_path = resolve_library_path(item.path)
    img_data = get_image_data_from_file(item_path, idx)
    return await send_image(img_data, size)


# ------------------------------- Album Routes ------------------------------- #


@artwork_pb.route("/album/<int:album_id>/art", methods=["GET"])
async def album_art(album_id: int):
    log.debug(f"Album art query for id:'{album_id}'")

    idx, size = parse_art_params()

    album = g.lib.get_album(album_id)
    if not album:
        raise NotFoundException(
            f"Album with beets_id:'{album_id}' not found in beets db."
        )

    # Has art set on album level
    if album.artpath and idx == 0:
        art_path = resolve_library_path(album.artpath)
        if not os.path.exists(art_path):
            raise IntegrityException(
                f"Album art file '{art_path}' does not exist for album beets_id:'{album_id}'."
            )
        return await send_image(BytesIO(open(art_path, "rb").read()), size)

    # Otherwise use embedded from track
    items = album.items()
    if not items or len(items) < 1:
        raise IntegrityException(f"Album has no items: '{album_id}'.")

    return redirect(
        url_for(
            ".item_art",
            item_id=items[0].id,
            index=idx,
            size=request.args.get("size", "small"),
        )
    )


# -------------------------------- File Routes ------------------------------- #


@artwork_pb.route("/files/<string:filepath>/nArtworks", methods=["GET"])
async def file_art_idx(filepath: str):
    """Get the number of images for a file."""
    filepath = bytes.fromhex(filepath).decode("utf-8")
    count = get_image_count_from_file(filepath)
    return jsonify({"count": count}), 200


@artwork_pb.route("/file/<string:filepath>/art", methods=["GET"])
async def file_art(filepath: str):
    filepath = bytes.fromhex(filepath).decode("utf-8")
    idx, size = parse_art_params()
    img_data = get_image_data_from_file(filepath, idx)
    return await send_image(img_data, size)


# ---------------------------------- Utils ----------------------------------- #


def _resize(img_data: BytesIO, size: tuple[int, int]) -> BytesIO:
    image = PILImage.open(img_data)
    image.thumbnail(size)
    image_io = BytesIO()
    image.convert("RGB").save(image_io, format="png")
    image_io.seek(0)
    return image_io
