import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.services.ocr_service import ALLOWED_IMAGE_TYPES, MAX_IMAGE_BYTES

# Filenames we generate are 32 hex chars + a known extension; reject anything else.
_VALID_ATTACHMENT_RE = re.compile(r"^[a-f0-9]{32}\.(jpg|png|webp|gif)$")

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "chat"
EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


async def save_chat_image(file: UploadFile) -> str:
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use JPEG, PNG, or WebP.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 5 MB)")

    ext = EXT_BY_MIME.get(content_type, ".jpg")
    filename = f"{uuid.uuid4().hex}{ext}"
    path = ensure_upload_dir() / filename
    path.write_bytes(data)
    return f"/api/chat/attachments/{filename}"


def resolve_attachment_path(filename: str) -> Path:
    # Whitelist the exact filename shape, then verify the resolved path stays
    # inside the upload dir (defends against traversal incl. Windows quirks).
    if not _VALID_ATTACHMENT_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    base = ensure_upload_dir().resolve()
    path = (base / filename).resolve()
    if not path.is_relative_to(base):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment not found")
    return path
