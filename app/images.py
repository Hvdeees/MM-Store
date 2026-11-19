"""Product photos.

Every upload is opened and re-encoded by Pillow instead of being saved as-is:
- a file that isn't really an image (or a disguised script) is refused;
- phone photos are turned upright (EXIF rotation) and stripped of their metadata (GPS location!);
- photos are shrunk to 800 px: a 12 MB phone photo becomes ~80 KB, so the till stays fast.
Files get random names chosen by the server, so an uploaded name like "../../etc/passwd" can't do anything.
"""
import io
import uuid

from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

MAX_UPLOAD_BYTES = 10 * 1024 * 1024        # 10 MB
MAX_PIXELS = 50_000_000                    # refuses "decompression bombs" (tiny file, gigantic image)
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
SIZE = (800, 800)

PRODUCTS_DIR = settings.media_dir / "products"


def ensure_media_dir() -> None:
    PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)


def save_product_image(data: bytes) -> str:
    """Validate, clean and save an uploaded photo. Returns the new file name."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Photo trop lourde (10 Mo maximum)")
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "Ce fichier n'est pas une photo (JPG, PNG ou WebP)")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS or probe.width * probe.height > MAX_PIXELS:
                raise invalid
            probe.verify()                                  # detects truncated / corrupted files
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)          # upright, like on the phone screen
            image.thumbnail(SIZE)
            if image.mode != "RGB":                         # transparent PNG -> white background
                background = Image.new("RGB", image.size, "white")
                rgba = image.convert("RGBA")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            ensure_media_dir()
            filename = f"{uuid.uuid4().hex}.jpg"
            image.save(PRODUCTS_DIR / filename, "JPEG", quality=85, optimize=True)  # no EXIF kept
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise invalid
    return filename


def delete_product_image(filename: str | None) -> None:
    if filename:
        (PRODUCTS_DIR / filename).unlink(missing_ok=True)
