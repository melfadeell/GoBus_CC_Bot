"""Arabic OCR post-processing (ported from DMS text_extraction_and_ocr)."""

import re
import unicodedata

import phunspell

_AL = "ال"
_LA = "لا"

_LTR_RUN_RE = re.compile(
    r"[A-Za-z0-9"
    r"٠-٩"
    r"۰-۹"
    r"/.\-:,+%()@#&$*=_\[\]{}|\\<>"
    r"]+"
)

_REVERSED_PARENS_RE = re.compile(r"\)\s*([٠-٩۰-۹0-9]+)\s*\(")

_ARABIC_TO_WESTERN = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩"
    "۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

_LIGATURE_REPLACEMENTS = [
    ("هللا", "الله"),
    ("اال", "الا"),
    ("لال", "للا"),
    ("أل", "لأ"),
    ("إل", "لإ"),
    ("لإي", "إلي"),
    ("لإى", "إلى"),
    ("لإا", "إلا"),
    ("اآل", "الآ"),
]

_processor: "ArabicTextProcessor | None" = None


class ArabicTextProcessor:
    def __init__(self) -> None:
        self._ar_dict = phunspell.Phunspell("ar")

    def process_ocr_text(self, text: str) -> str:
        text = self.fix_rtl_text(text)
        text = self.fix_ligatures_with_dict(text)
        text = self._fix_reversed_parens(text)
        return self._arabic_digits_to_western(text)

    def fix_rtl_text(self, text: str) -> str:
        lines = text.split("\n")
        fixed = [self._fix_rtl_line(line) if self._has_rtl(line) else line for line in lines]
        return self._fix_ligatures("\n".join(fixed))

    def fix_ligatures_with_dict(self, text: str) -> str:
        wal = "و" + _AL
        wla = "و" + _LA
        words = text.split(" ")
        fixed: list[str] = []
        for word in words:
            if word == _AL:
                fixed.append(_LA)
            elif word == wal:
                fixed.append(wla)
            else:
                idx = word.find(_AL, 2 if word.startswith(_AL) else 1)
                fixed.append(self._try_fix_al_to_la(word) if idx > 0 else word)
        return " ".join(fixed)

    @staticmethod
    def _has_rtl(line: str) -> bool:
        return any(unicodedata.bidirectional(c) in ("R", "AL") for c in line)

    def _fix_rtl_line(self, line: str) -> str:
        reversed_line = line[::-1]
        return _LTR_RUN_RE.sub(lambda m: m.group()[::-1], reversed_line)

    def _fix_ligatures(self, text: str) -> str:
        for wrong, right in _LIGATURE_REPLACEMENTS:
            text = text.replace(wrong, right)
        return text

    def _try_fix_al_to_la(self, word: str) -> str:
        if self._ar_dict.lookup(word):
            return word
        search_from = 2 if word.startswith(_AL) else 1
        idx = word.find(_AL, search_from)
        while idx != -1:
            candidate = word[:idx] + _LA + word[idx + 2 :]
            if self._ar_dict.lookup(candidate):
                return candidate
            idx = word.find(_AL, idx + 1)
        return word

    def _fix_reversed_parens(self, text: str) -> str:
        return _REVERSED_PARENS_RE.sub(lambda m: "(" + m.group(1) + ")", text)

    def _arabic_digits_to_western(self, text: str) -> str:
        return text.translate(_ARABIC_TO_WESTERN)


def get_arabic_processor() -> ArabicTextProcessor:
    global _processor
    if _processor is None:
        _processor = ArabicTextProcessor()
    return _processor
