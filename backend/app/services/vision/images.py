"""Image validation and preparation before OCR.

- Formats are identified by magic bytes, never by filename or client MIME.
- Oversized images (decompression bombs) are refused before decoding.
- Phone photos are rotated using their EXIF orientation, downscaled, and re-encoded as JPEG, which
  drops EXIF metadata such as GPS location before the image is stored or sent anywhere.
"""

from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from app.services.vision.base import VisionError

IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_PIXELS = 50_000_000  # ~ a 8K photo; larger is refused
MAX_SIDE = 3000  # plenty for OCR, keeps requests small


def sniff_image(data: bytes) -> str | None:
    head = data[:16]
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"):
        return "image/heic"
    return None


def prepare_image(data: bytes, mime: str) -> tuple[bytes, str]:
    """Returns (bytes, mime) ready for OCR/storage. HEIC is passed through unchanged (Pillow can't decode it
    without a plugin; Apple Vision and Gemini both read it)."""
    if mime == "image/heic":
        return data, mime
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > MAX_PIXELS:
                raise VisionError("IMAGE_TOO_LARGE", "This image is too large to read. Take the photo at a lower resolution and try again.")
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            if max(im.size) > MAX_SIDE:
                im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=90, optimize=True)  # no exif= → metadata dropped
            return out.getvalue(), "image/jpeg"
    except Image.DecompressionBombError as exc:
        raise VisionError("IMAGE_TOO_LARGE", "This image is too large to read. Take the photo at a lower resolution and try again.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise VisionError("UNREADABLE_IMAGE", "This image couldn't be opened. Take the photo again or upload a JPG or PNG.") from exc
