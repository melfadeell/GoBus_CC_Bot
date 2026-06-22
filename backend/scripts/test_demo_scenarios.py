"""Behavioral regression suite for the GoBus bot retrieval logic.

Runs DIRECTLY against retrieve_context (no HTTP, no OpenAI cost). Each scenario
asserts the KB intent/labels and — for trips — structural behavior such as
price ordering, "latest" direction, explicit counts, follow-up route memory,
and the no-data fallback hint.

Usage (from backend/):  venv/Scripts/python.exe -m scripts.test_demo_scenarios
"""

import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app.database import SessionLocal
from app.services.kb_retrieval import _HISTORY_SEP, retrieve_context

LABELS = ["Trips", "Stations", "Destinations", "Services", "FAQ", "About", "Policies"]
NO_TRIP_HINT = "no matching upcoming trips"


@dataclass
class S:
    name: str
    query: str
    require: list[str] = field(default_factory=list)      # labels that must appear
    history: list[str] = field(default_factory=list)      # prior turns (oldest→newest)
    min_rows: int | None = None                           # min [Trips] data rows
    max_rows: int | None = None                           # max [Trips] data rows
    price_order: str | None = None                        # 'asc' | 'desc'
    latest: bool = False                                  # last row holds the max date
    contains: list[str] = field(default_factory=list)
    not_contains: list[str] = field(default_factory=list)


SCENARIOS: list[S] = [
    # --- core intent routing ---
    S("services vs gomini", "What is the difference between GoBus and GoMini?", require=["Services"]),
    S("station nasr city", "Nearest GoBus station in Nasr City?", require=["Stations"]),
    S("booking how-to", "How can I book a GoBus ticket?", require=["FAQ"]),
    S("hotline", "What is the GoBus hotline?", require=["FAQ"]),
    S("about company", "Who owns GoBus and when was it founded?", require=["About"]),
    S("golemo service", "What is GoLemo and what services does it offer?", require=["Services"]),
    S("policy cancel", "What is the cancellation and refund policy?", require=["Policies"]),
    S("destination hurghada", "Tell me about Hurghada as a destination", require=["Destinations"]),
    S("station giza map", "Where is the Giza station and what is the map link?", require=["Stations"]),
    S("destinations list", "What destinations does GoBus serve?", require=["Destinations"]),
    # --- trips: schedules & routes ---
    S("cairo-alex schedule", "Cairo - Alexandria trip schedules", require=["Trips"], min_rows=1),
    S("next to dahab", "What is the next trip to Dahab?", require=["Trips"], min_rows=1),
    S("hurghada price", "Trip prices from Cairo to Hurghada", require=["Trips"], min_rows=1),
    S("seats sharm tomorrow", "Seats available tomorrow to Sharm El Sheikh?", require=["Trips"], min_rows=1),
    S("marsa alam", "Cairo to Marsa Alam schedule", require=["Trips"], min_rows=1),
    S("port said open", "Are there open trips from Cairo to Port Said?", require=["Trips"], min_rows=1),
    S("luxor tomorrow", "Trip from Cairo to Luxor tomorrow", require=["Trips"], min_rows=1),
    S("nuweiba seats", "Seats available on Cairo to Nuweiba trips?", require=["Trips"], min_rows=1),
    # --- trips: new behavior (ordering / counts / latest) ---
    S("latest to dahab", "What is the latest trip to Dahab?", require=["Trips"], min_rows=1, latest=True),
    S("latest 5 alex", "latest 5 trips from cairo to alexandria", require=["Trips"], min_rows=2, max_rows=5),
    S("cheapest alex", "cheapest trip from cairo to alexandria", require=["Trips"], min_rows=2, price_order="asc"),
    S("most expensive alex", "most expensive trip cairo to alexandria", require=["Trips"], min_rows=2, price_order="desc"),
    S("cheapest arabic", "أرخص رحلة من القاهرة إلى الإسكندرية", require=["Trips"], min_rows=2, price_order="asc"),
    # --- trips: arabic / mixed / variants ---
    S("arabic plain alef", "مواعيد رحلات الاسكندرية", require=["Trips"], min_rows=1),
    S("arabic cairo-alex", "مواعيد رحلة القاهرة – الإسكندرية", require=["Trips"], min_rows=1),
    S("mixed ar-en", "عايز رحلات to alexandria", require=["Trips"], min_rows=1),
    S("alex abbreviation", "what is the latest trip from cairo to alex", require=["Trips"], min_rows=1),
    # --- trips: follow-ups with conversation memory ---
    S("followup latest 5", "the latest 5",
      history=["cairo to alexandria schedules", "here are the alexandria trips"],
      require=["Trips"], min_rows=1, max_rows=5, contains=["الإسكندرية"]),
    S("followup recency", "the latest 5",
      history=["trips to hurghada", "here are hurghada trips",
               "cairo to alexandria schedules", "here are alexandria trips"],
      require=["Trips"], contains=["الإسكندرية"], not_contains=["الغردقة"]),
    S("followup bare number", "5",
      history=["cheapest trips cairo to dahab", "here are dahab trips"],
      require=["Trips"], min_rows=1, max_rows=5, contains=["دهب"]),
    # --- no-data / robustness ---
    S("unknown city", "trips to atlantis", contains=[NO_TRIP_HINT]),
    S("typo city", "trips to Careo to Hurghada", require=["Trips"], min_rows=1),
    # --- arabic intents ---
    S("arabic services", "إيه الفرق بين GoBus و GoMini؟", require=["Services"]),
    S("arabic station", "فين أقرب محطة في مدينة نصر؟", require=["Stations"]),
    S("arabic booking", "كيف أحجز تذكرة GoBus؟", require=["FAQ"]),
    S("arabic hotline", "إيه الخط الساخن؟", require=["FAQ"]),
]


def check(db, s: S) -> list[str]:
    """Return a list of failure messages (empty == pass)."""
    history_text = _HISTORY_SEP.join(s.history) if s.history else None
    debug: dict = {}
    ctx = retrieve_context(db, s.query, history_text=history_text, debug=debug)
    fails: list[str] = []

    found = [lbl for lbl in LABELS if f"[{lbl}]" in ctx]
    for lbl in s.require:
        if lbl not in found:
            fails.append(f"missing label [{lbl}] (found {found})")

    # Trips are now structured (debug["trips"]) instead of text rows.
    trips = debug.get("trips", [])
    if s.min_rows is not None and len(trips) < s.min_rows:
        fails.append(f"expected >= {s.min_rows} trips, got {len(trips)}")
    if s.max_rows is not None and len(trips) > s.max_rows:
        fails.append(f"expected <= {s.max_rows} trips, got {len(trips)}")

    if s.price_order:
        prices = [t["price_egp"] for t in trips]
        if prices != sorted(prices, reverse=(s.price_order == "desc")):
            fails.append(f"prices not {s.price_order}: {prices}")

    if s.latest and trips:
        dts = [date.fromisoformat(t["date"]) for t in trips]
        if dts[-1] != max(dts):
            fails.append(f"latest: last row {dts[-1]} != max {max(dts)}")

    for c in s.contains:
        if c not in ctx:
            fails.append(f"missing text: {c!r}")
    for c in s.not_contains:
        if c in ctx:
            fails.append(f"unexpected text: {c!r}")

    return fails


def main() -> int:
    db = SessionLocal()
    passed = failed = 0
    print("GOBUS BOT BEHAVIORAL RETRIEVAL SUITE")
    print("=" * 92)
    for s in SCENARIOS:
        fails = check(db, s)
        if fails:
            failed += 1
            print(f"FAIL | {s.name}: {s.query[:55]}")
            for f in fails:
                print(f"       - {f}")
        else:
            passed += 1
            print(f"PASS | {s.name}")
    print("=" * 92)
    print(f"Summary: {passed} passed, {failed} failed, {len(SCENARIOS)} total")
    db.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
