import io
import logging

import fitz

from app.services.ocr_service import ALLOWED_IMAGE_TYPES, extract_text_from_image

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_FILE_BYTES = 10 * 1024 * 1024


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _extract_pdf(data: bytes) -> str:
    doc = fitz.open(stream=data, filetype="pdf")
    parts: list[str] = []
    try:
        for page in doc:
            text = (page.get_text() or "").strip()
            if text:
                parts.append(text)
                continue
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            ocr_text = extract_text_from_image(img_bytes)
            if ocr_text:
                parts.append(ocr_text)
    finally:
        doc.close()
    return "\n\n".join(parts).strip()


def extract_text_from_upload(data: bytes, filename: str, content_type: str | None = None) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("File too large (max 10 MB)")

    ext = f".{_extension(filename)}"
    mime = (content_type or "").lower()

    if ext in TEXT_EXTENSIONS or mime.startswith("text/"):
        return data.decode("utf-8", errors="replace").strip()

    if ext in PDF_EXTENSIONS or mime == "application/pdf":
        return _extract_pdf(data)

    if ext in IMAGE_EXTENSIONS or mime in ALLOWED_IMAGE_TYPES:
        return extract_text_from_image(data)

    raise ValueError("Unsupported file type. Use TXT, MD, PDF, or an image (JPEG/PNG/WebP).")
