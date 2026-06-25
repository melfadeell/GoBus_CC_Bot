import io
import logging
import os
import re
import shutil

import pytesseract
from PIL import Image, ImageEnhance, ImageOps

from app.config import get_settings
from app.services.arabic_text import get_arabic_processor

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
OCR_MAX_DIM = 3200
OCR_MIN_DIM = 1400
TESSERACT_PSMS = ("3", "6", "11")

_arabic_re = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_arabic_word_re = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+")
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


def _enhance_for_ocr(image: Image.Image) -> Image.Image:
    """Upscale small screenshots and boost contrast for dense Arabic/English text."""
    width, height = image.size
    max_dim = max(width, height)
    if max_dim < OCR_MIN_DIM:
        scale = OCR_MIN_DIM / max_dim
        image = image.resize((int(width * scale), int(height * scale)), Image.LANCZOS)

    gray = ImageOps.autocontrast(image.convert("L"))
    gray = ImageEnhance.Contrast(gray).enhance(1.6)
    return ImageEnhance.Sharpness(gray).enhance(1.3)


def _clean_lines(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def _has_arabic(text: str) -> bool:
    return bool(_arabic_re.search(text))


def _run_tesseract(image: Image.Image, *, lang: str, psm: str) -> str:
    return pytesseract.image_to_string(image, lang=lang, config=f"--psm {psm}").strip()


def _run_tesseract_lines(image: Image.Image, *, lang: str, psm: str) -> tuple[str, float]:
    data = pytesseract.image_to_data(
        image,
        lang=lang,
        config=f"--psm {psm}",
        output_type=pytesseract.Output.DICT,
    )
    lines_by_key: dict[tuple[int, int], list[tuple[int, str]]] = {}
    confidences: list[int] = []

    for index, text in enumerate(data["text"]):
        token = text.strip()
        if not token:
            continue
        confidence = int(data["conf"][index])
        if confidence < 0:
            continue
        block = int(data["block_num"][index])
        line = int(data["line_num"][index])
        word_num = int(data["word_num"][index])
        lines_by_key.setdefault((block, line), []).append((word_num, token))
        confidences.append(confidence)

    rendered_lines = [
        " ".join(word for _, word in sorted(words))
        for _, words in sorted(lines_by_key.items())
    ]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return "\n".join(rendered_lines).strip(), avg_confidence


def _score_english_ocr(text: str) -> float:
    cleaned = text.strip()
    return float(len(cleaned)) if cleaned else 0.0


def _score_arabic_ocr(text: str, avg_confidence: float) -> float:
    cleaned = _clean_lines(get_arabic_processor().process_ocr_text(text))
    if not cleaned:
        return 0.0

    processor = get_arabic_processor()
    words = _arabic_word_re.findall(cleaned)
    valid_words = sum(
        1 for word in words if len(word) >= 3 and processor._ar_dict.lookup(word)
    )
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    short_lines = sum(1 for line in lines if len(_arabic_re.findall(line)) <= 2)
    long_lines = sum(1 for line in lines if len(_arabic_re.findall(line)) >= 8)

    return avg_confidence * 3 + valid_words * 60 + long_lines * 35 - short_lines * 25


def _best_english_ocr(image: Image.Image) -> str:
    best_text = ""
    best_score = 0.0
    for psm in ("3", "6"):
        try:
            raw = _run_tesseract(image, lang="eng", psm=psm)
        except Exception as exc:
            logger.debug("English OCR failed for psm=%s: %s", psm, exc)
            continue
        cleaned = _clean_lines(raw)
        score = _score_english_ocr(cleaned)
        if score > best_score:
            best_score = score
            best_text = cleaned
    return best_text


def _best_arabic_ocr(image: Image.Image) -> str:
    best_text = ""
    best_score = 0.0
    for psm in TESSERACT_PSMS:
        try:
            raw, avg_confidence = _run_tesseract_lines(image, lang="ara", psm=psm)
        except Exception as exc:
            logger.debug("Arabic OCR failed for psm=%s: %s", psm, exc)
            continue
        score = _score_arabic_ocr(raw, avg_confidence)
        if score <= best_score:
            continue
        best_score = score
        best_text = _clean_lines(get_arabic_processor().process_ocr_text(raw))
    return best_text


def extract_text_from_image(data: bytes) -> str:
    """English via Tesseract eng; Arabic via Tesseract ara + light post-processing."""
    _configure_tesseract()
    image = _enhance_for_ocr(_prepare_image(data))

    eng_text = _best_english_ocr(image)
    ara_text = _best_arabic_ocr(image)

    if ara_text and eng_text:
        if _has_arabic(ara_text):
            return ara_text if len(ara_text) >= len(eng_text) * 0.5 else f"{ara_text}\n\n{eng_text}"
        return eng_text

    if ara_text and _has_arabic(ara_text):
        return ara_text

    return eng_text or ara_text
