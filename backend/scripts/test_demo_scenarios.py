"""Verify demo chat scenarios load the expected KB context types."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app.database import SessionLocal
from app.services.kb_retrieval import (
    _detect_content_intents,
    _expand_search_terms,
    retrieve_context,
)

LABELS = ["Trips", "Stations", "Destinations", "Services", "FAQ", "About", "Policies"]

SCENARIOS = [
    ("What is the difference between GoBus and GoMini?", ["Services"], ["FAQ"]),
    ("Nearest GoBus station in Nasr City?", ["Stations"], []),
    ("Cairo – Alexandria trip schedules", ["Trips"], []),
    ("What is the next trip to Dahab?", ["Trips"], []),
    ("How can I book a GoBus ticket?", ["FAQ"], []),
    ("Trip prices from Cairo to Hurghada", ["Trips"], []),
    ("Tell me about GoBus destinations", ["Destinations"], ["FAQ"]),
    ("What is the GoBus hotline?", ["FAQ"], []),
    ("Seats available tomorrow to Sharm El Sheikh?", ["Trips"], []),
    ("What bus classes does GoBus offer?", ["FAQ"], []),
    # 20 additional coverage scenarios
    ("Who owns GoBus and when was it founded?", ["About"], []),
    ("What is GoLemo and what services does it offer?", ["Services"], ["FAQ"]),
    ("What is the cancellation and refund policy?", ["Policies"], []),
    ("Tell me about Hurghada as a destination", ["Destinations"], []),
    ("Where is the Giza station and what is the map link?", ["Stations"], []),
    ("Cairo to Marsa Alam schedule", ["Trips"], []),
    ("Are there open trips from Cairo to Port Said?", ["Trips"], []),
    ("How do I know trip schedules?", ["FAQ"], []),
    ("What destinations does GoBus serve?", ["Destinations"], ["FAQ"]),
    ("Nearest GoBus station in Heliopolis?", ["Stations"], []),
    ("What is the price for Cairo to Alexandria elite class?", ["Trips"], []),
    ("Can I book tickets online?", ["FAQ"], []),
    ("Tell me about GoBus company history", ["About"], []),
    ("What are the terms and conditions?", ["Policies"], []),
    ("Tell me about Dahab", ["Destinations"], []),
    ("What is the difference between standard and elite?", ["FAQ"], []),
    ("Trip from Cairo to Luxor tomorrow", ["Trips"], []),
    ("Where is Madinaty station?", ["Stations"], []),
    ("What is GoMini?", ["Services"], ["FAQ"]),
    ("Seats available on Cairo to Nuweiba trips?", ["Trips"], []),
    ("إيه الفرق بين GoBus و GoMini؟", ["Services"], ["FAQ"]),
    ("فين أقرب محطة في مدينة نصر؟", ["Stations"], []),
    ("مواعيد رحلة القاهرة – الإسكندرية", ["Trips"], []),
    ("كيف أحجز تذكرة GoBus؟", ["FAQ"], []),
    ("إيه الخط الساخن؟", ["FAQ"], []),
]


def found_labels(ctx: str) -> list[str]:
    return [label for label in LABELS if f"[{label}]" in ctx]


def main() -> int:
    db = SessionLocal()
    passed = 0
    failed = 0
    print("DEMO SCENARIO RETRIEVAL TEST")
    print("=" * 90)

    for question, required, optional in SCENARIOS:
        terms = _expand_search_terms(question, db)
        intents = sorted(_detect_content_intents(question, terms))
        ctx = retrieve_context(db, question)
        found = found_labels(ctx)
        has_content = len(ctx.strip()) > 50
        missing = [r for r in required if r not in found]
        ok = has_content and not missing

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"{status} | {question[:60]}")
        print(f"       required={required} optional={optional}")
        print(f"       found={found} intents={intents}")
        if not ok:
            if missing:
                print(f"       missing labels: {missing}")
            if not has_content:
                print("       context too short or empty")
        print()

    print("=" * 90)
    print(f"Summary: {passed} passed, {failed} failed, {len(SCENARIOS)} total")
    db.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
