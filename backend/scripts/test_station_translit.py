"""Validate the Arabic↔Latin transliteration station matcher.

Pure-Python (no DB, no OpenAI): checks that English / Franco-Arabic spellings of
the real GoBus station names resolve to the correct Arabic name via the romanized
fuzzy matcher, and that unrelated queries do NOT false-positive.

Usage (from backend/):  venv/Scripts/python.exe -m scripts.test_station_translit
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app.services.kb_retrieval import _TRANSLIT_MATCH_THRESHOLD, _romanized_similarity
from app.utils.text_utils import romanized_key

# The real station names (from the official station list).
STATION_NAMES = [
    "عبد المنعم رياض", "رمسيس - جوباص", "القللى", "السادس من اكتوبر", "مدينتي",
    "مدينة الرحاب", "الجيزة", "الماظة", "مكتب نادي السكة", "محطة مدينه نصر",
    "التجمع الخامس", "هايبر وان (الشيخ زايد)", "جسر السويس", "سفاجا", "مرسى علم",
    "القصير", "قرية الجونة", "سوما باي", "مكادى", "سهل حشيش", "السقالة", "الغردقة",
    "مكتب الأحياء", "رأس سدر", "قرية تافيرا", "موسي كوست", "مطارما باي", "لاهاسيندا",
    "دهب", "الرويسات", "جوباص شرم", "الوطنية", "عرب سات - نبق", "نويبع", "طابا هايتس",
    "محرم بك", "ميامى", "سيدي جابر _ سموحة", "مارينا 5", "مراسى (الساحل الشمالى)",
    "مرسى مطروح", "الضبعة", "مارينا 7", "جراند اوشن", "بورتو ساوث بيتش", "كانكون",
    "بورتو السخنة", "قنا المحطة", "المحلة", "طنطا", "بورسعيد وسط البلد",
    "ميناء بورسعيد", "أسيوط الهلالي", "ملوي جوباص", "المنيا جوباص", "الأقصر",
    "المنصورة", "الاسماعيلية",
]

# (english/franco query, expected arabic station name)
POSITIVE_CASES = [
    ("Gesr El Suez", "جسر السويس"),
    ("gesr elsuez", "جسر السويس"),
    ("Hurghada", "الغردقة"),
    ("Safaga", "سفاجا"),
    ("Marsa Alam", "مرسى علم"),
    ("Dahab", "دهب"),
    ("Nuweiba", "نويبع"),
    ("Tanta", "طنطا"),
    ("El Mansoura", "المنصورة"),
    ("Mansoura", "المنصورة"),
    ("Ismailia", "الاسماعيلية"),
    ("Mahram Bek", "محرم بك"),
    ("Sidi Gaber", "سيدي جابر _ سموحة"),
    ("Kankoun", "كانكون"),
    ("Mahalla", "المحلة"),
    ("Sahl Hasheesh", "سهل حشيش"),
    ("Ras Sedr", "رأس سدر"),
    ("Taba Heights", "طابا هايتس"),
]

# queries that must NOT match any station above threshold
NEGATIVE_CASES = [
    "I want to book a ticket",
    "what are your prices",
    "refund policy",
]

# Non-phonetic exonyms (e.g. Luxor=Al-Uqsur, Port Said=Bursaid) that transliteration
# alone cannot bridge — these are handled by the STATION_ALIASES / DESTINATION_ALIASES
# maps in the real pipeline, not by this fuzzy layer. Listed here for documentation.
ALIAS_ONLY = ["Luxor", "Port Said"]


def best_match(query: str) -> tuple[str | None, float]:
    qk = romanized_key(query)
    best_name, best_score = None, 0.0
    for name in STATION_NAMES:
        score = _romanized_similarity(qk, romanized_key(name))
        if score > best_score:
            best_name, best_score = name, score
    return best_name, best_score


def main() -> int:
    failures = 0
    print(f"threshold = {_TRANSLIT_MATCH_THRESHOLD}\n")

    print("POSITIVE cases (English/Franco → Arabic):")
    for query, expected in POSITIVE_CASES:
        name, score = best_match(query)
        ok = name == expected and score >= _TRANSLIT_MATCH_THRESHOLD
        flag = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"  [{flag}] {query!r:24} → {name!r} ({score:.2f})  expected {expected!r}")

    print("\nNEGATIVE cases (must NOT match a station):")
    for query in NEGATIVE_CASES:
        name, score = best_match(query)
        ok = score < _TRANSLIT_MATCH_THRESHOLD
        flag = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"  [{flag}] {query!r:24} → best {name!r} ({score:.2f})")

    print("\nALIAS-ONLY (non-phonetic; covered by alias maps, not transliteration):")
    for query in ALIAS_ONLY:
        name, score = best_match(query)
        print(f"  [info] {query!r:24} → best {name!r} ({score:.2f})")

    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
