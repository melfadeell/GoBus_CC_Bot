import io
import logging
import os
import re
import shutil

import pytesseract
from PIL import Image, ImageOps

from app.config import get_settings
from app.services.arabic_text import get_arabic_processor

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
OCR_MAX_DIM = 2400
TESSERACT_PSM = "--psm 6"

_arabic_re = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_tesseract_configured = False


def _configure_tesseract() -> None:
    global _tesseract_configured
    if _tesseract_configured:
        return

    settings = get_settings()
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    elif shutil.which("tesseract") is None:
        default_win = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.isfile(default_win):
            pytesseract.pytesseract.tesseract_cmd = default_win

    _tesseract_configured = True


def tesseract_available() -> bool:
    _configure_tesseract()
    cmd = pytesseract.pytesseract.tesseract_cmd
    return bool(cmd and os.path.isfile(cmd)) or shutil.which("tesseract") is not None


def _prepare_image(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    if max(image.size) > OCR_MAX_DIM:
        image.thumbnail((OCR_MAX_DIM, OCR_MAX_DIM), Image.LANCZOS)
    return image


def _clean_lines(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def _has_arabic(text: str) -> bool:
    return bool(_arabic_re.search(text))


def _ocr_english(image: Image.Image) -> str:
    return pytesseract.image_to_string(image, lang="eng", config=TESSERACT_PSM).strip()


def _ocr_arabic(image: Image.Image) -> str:
    raw = pytesseract.image_to_string(image, lang="ara", config=TESSERACT_PSM).strip()
    if not raw:
        return ""
    return get_arabic_processor().process_ocr_text(raw)


def extract_text_from_image(data: bytes) -> str:
    """English via Tesseract eng; Arabic via Tesseract ara + DMS post-processing."""
    _configure_tesseract()
    image = _prepare_image(data)

    eng_text = _clean_lines(_ocr_english(image))
    ara_text = _clean_lines(_ocr_arabic(image))

    if ara_text and eng_text:
        if _has_arabic(ara_text):
            return ara_text if len(ara_text) >= len(eng_text) * 0.5 else f"{ara_text}\n\n{eng_text}"
        return eng_text

    if ara_text and _has_arabic(ara_text):
        return ara_text

    return eng_text or ara_text
