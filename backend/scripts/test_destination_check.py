"""Validate the single-city 'does GoBus go to X?' destination matcher.

Pure-Python (no DB, no OpenAI): patches the served-destination list and the alias
expansion so we can assert that English / Franco-Arabic / Arabic spellings of a
served city resolve to its canonical Arabic name, and that unserved or unrelated
queries return None.

Usage (from backend/):  venv/Scripts/python.exe -m scripts.test_destination_check
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app.services import kb_retrieval
from app.services.kb_retrieval import DESTINATION_ALIASES, _match_served_destination

# The served destinations shown as chips in the live UI.
SERVED = [
    "شرم الشيخ", "الإسكندرية", "الغردقة", "العين السخنة", "بورسعيد",
    "دهب", "مرسى علم", "مكادى", "نويبع", "الساحل الشمالى", "الأقصر",
]


def _fake_expand(query: str, db) -> list[str]:
    """Alias-only expansion (mirrors the English/Arabic branches of the real one)."""
    terms: list[str] = []
    q_lower = query.lower()
    for en_key, ar_names in DESTINATION_ALIASES.items():
        if en_key in q_lower:
            terms.extend(ar_names)
    for ar_names in DESTINATION_ALIASES.values():
        for ar in ar_names:
            if ar in query:
                terms.append(ar)
    return terms


# (query, expected canonical name or None)
CASES = [
    ("Sharm El Sheikh", "شرم الشيخ"),
    ("sharm", "شرم الشيخ"),
    ("شرم الشيخ", "شرم الشيخ"),
    ("هل جوباص بيروح الغردقة؟", "الغردقة"),
    ("Hurghada", "الغردقة"),
    ("Luxor", "الأقصر"),
    ("Dahab", "دهب"),
    ("Marsa Alam", "مرسى علم"),
    ("Alexandria", "الإسكندرية"),
    ("Port Said", "بورسعيد"),
    # Not served / unrelated
    ("Aswan", None),
    ("أسوان", None),
    ("London", None),
]


def main() -> int:
    kb_retrieval._all_route_destinations = lambda db: list(SERVED)
    kb_retrieval._expand_search_terms = _fake_expand

    failures = 0
    print("Destination yes/no check:\n")
    for query, expected in CASES:
        got = _match_served_destination(None, query)
        ok = got == expected
        if not ok:
            failures += 1
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {query!r:32} → {got!r}  expected {expected!r}")

    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
